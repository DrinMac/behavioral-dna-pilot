'use strict';

const app = document.getElementById('app');
const progressLabel = document.getElementById('progressLabel');
const progressCount = document.getElementById('progressCount');
const progressFill = document.getElementById('progressFill');
const participantBadge = document.getElementById('participantBadge');

const state = {
  config: null,
  token: localStorage.getItem('bd_participant_token') || '',
  recoveryPin: localStorage.getItem('bd_recovery_pin') || '',
  me: null,
  profileDraft: null,
  device: null,
  activeSession: null,
  initialEvents: [],
  fixedEvents: [],
  freeEvents: [],
  fixedText: '',
  freeText1: '',
  freeText2: '',
  analysis: null,
};

const SCOPE_COPY = {
  initial: ['Initial', 'Registration typing'],
  fixed: ['Fixed Text', 'Standard passage'],
  free: ['Free Text', 'Two personal responses'],
  combined: ['Combined', 'Fixed + Free telemetry'],
};

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;',
  }[character]));
}

function setProgress(step, label, total = 7) {
  const safeStep = Math.max(0, Math.min(step, total));
  progressLabel.textContent = label;
  progressCount.textContent = safeStep ? `Step ${safeStep} of ${total}` : '';
  progressFill.style.width = `${safeStep ? (safeStep / total) * 100 : 0}%`;
}

function updateParticipantBadge() {
  const code = state.me?.participant?.participant_code;
  if (!code) {
    participantBadge.hidden = true;
    participantBadge.textContent = '';
    return;
  }
  participantBadge.textContent = `Participant ${code}`;
  participantBadge.hidden = false;
}

function screen(body, actions = '', actionClass = '') {
  app.setAttribute('aria-busy', 'false');
  app.innerHTML = `
    <div class="screen">
      <div class="screen-body">${body}</div>
      ${actions ? `<div class="screen-action ${actionClass}">${actions}</div>` : ''}
    </div>`;
  window.scrollTo({top: 0, behavior: 'instant'});
}

function showLoading(message) {
  app.setAttribute('aria-busy', 'true');
  app.innerHTML = `<div class="loading-screen"><div class="loading-mark" aria-hidden="true"></div><p>${escapeHtml(message)}</p></div>`;
}

function showError(message) {
  const body = app.querySelector('.screen-body');
  if (!body) return;
  body.querySelector('.error-banner')?.remove();
  const banner = document.createElement('div');
  banner.className = 'error-banner';
  banner.setAttribute('role', 'alert');
  banner.textContent = message;
  body.prepend(banner);
  banner.scrollIntoView({behavior: 'smooth', block: 'center'});
}

async function api(path, options = {}, participantAuth = true) {
  const headers = {'Content-Type': 'application/json', ...(options.headers || {})};
  if (participantAuth && state.token) headers['X-Participant-Token'] = state.token;
  const response = await fetch(path, {...options, headers, cache: 'no-store'});
  const contentType = response.headers.get('content-type') || '';
  const data = contentType.includes('application/json') ? await response.json() : await response.text();
  if (!response.ok) throw new Error(data?.detail || data || 'Request failed');
  return data;
}

function detectDevice() {
  const ua = navigator.userAgent;
  let browser = 'Other browser';
  if (/Edg\//.test(ua)) browser = 'Microsoft Edge';
  else if (/OPR\//.test(ua)) browser = 'Opera';
  else if (/Chrome\//.test(ua)) browser = 'Google Chrome';
  else if (/Firefox\//.test(ua)) browser = 'Mozilla Firefox';
  else if (/Safari\//.test(ua)) browser = 'Apple Safari';

  let os = 'Other operating system';
  if (/Windows NT/.test(ua)) os = 'Windows';
  else if (/Mac OS X/.test(ua) && !/Mobile/.test(ua)) os = 'macOS';
  else if (/Android/.test(ua)) os = 'Android';
  else if (/iPhone|iPad|iPod/.test(ua)) os = 'iOS/iPadOS';
  else if (/Linux/.test(ua)) os = 'Linux';

  let deviceType = 'Desktop or laptop';
  if (/iPad|Tablet/.test(ua)) deviceType = 'Tablet';
  else if (/Mobile|Android|iPhone/.test(ua)) deviceType = 'Mobile phone';

  return {browser, os, device_type: deviceType, keyboard_type: 'Unknown'};
}

function createRecorder(root, blockPaste = false, options = {}) {
  const events = [];
  let sequence = 0;
  const startedAt = performance.now();
  let active = true;
  const segment = options.segment || null;
  const activityType = options.activityType || null;
  const fieldName = target => target?.name || target?.id || 'main';

  const record = (event, eventType) => {
    if (!active) return;
    const now = performance.now();
    events.push({
      sequence_no: sequence++,
      event_type: eventType,
      key: event.key || null,
      code: event.code || null,
      timestamp_ms: now,
      relative_time_ms: now - startedAt,
      field_name: fieldName(event.target),
      segment,
      activity_type: activityType,
      is_backspace: event.key === 'Backspace' || event.key === 'Delete',
      is_paste: eventType === 'paste',
      is_focus_event: eventType === 'focus' || eventType === 'blur',
      repeat: Boolean(event.repeat),
    });
  };

  const keydown = event => record(event, 'keydown');
  const keyup = event => record(event, 'keyup');
  const paste = event => {
    record(event, 'paste');
    if (blockPaste) {
      event.preventDefault();
      const message = root.querySelector('[data-capture-message]');
      if (message) message.textContent = 'Pasting is disabled. Please type the response naturally.';
    }
  };
  const focus = event => record(event, 'focus');
  const blur = event => record(event, 'blur');

  root.addEventListener('keydown', keydown, true);
  root.addEventListener('keyup', keyup, true);
  root.addEventListener('paste', paste, true);
  root.addEventListener('focusin', focus, true);
  root.addEventListener('focusout', blur, true);

  return {
    events,
    stop() {
      if (!active) return;
      active = false;
      root.removeEventListener('keydown', keydown, true);
      root.removeEventListener('keyup', keyup, true);
      root.removeEventListener('paste', paste, true);
      root.removeEventListener('focusin', focus, true);
      root.removeEventListener('focusout', blur, true);
    },
  };
}

function resetCaptureState(includeInitial = false) {
  if (includeInitial) state.initialEvents = [];
  state.fixedEvents = [];
  state.freeEvents = [];
  state.fixedText = '';
  state.freeText1 = '';
  state.freeText2 = '';
  state.analysis = null;
}

function selectedOption(value, current) {
  return value === current ? 'selected' : '';
}

function completedSessions() {
  return (state.me?.sessions || []).filter(session => session.status === 'completed');
}

function latestKeyboard() {
  return [...completedSessions()].reverse().find(session => session.keyboard_type && session.keyboard_type !== 'Unknown')?.keyboard_type || '';
}

function homePage() {
  setProgress(1, 'Study introduction');
  updateParticipantBadge();
  screen(`
    <div class="eyebrow">Participant study</div>
    <h1>Your typing rhythm can help us study continuous authentication.</h1>
    <p class="lead">This one-week longitudinal study examines whether ordinary keystroke timing can help verify that the original user remains active after login.</p>

    <div class="hero-panel">
      <h2>What you will do</h2>
      <p>Complete one fixed-text activity and two short free-text responses during each session. The target is at least ${escapeHtml(state.config.target_sessions)} sessions, preferably across several days.</p>
    </div>

    <div class="info-grid">
      <div class="info-card"><span class="info-number">01</span><strong>Typing telemetry</strong><span>Keydown and keyup timing, pauses, corrections, speed, and consistency.</span></div>
      <div class="info-card"><span class="info-number">02</span><strong>Participant profile</strong><span>Age, gender, occupation, educational attainment, city, and province/state.</span></div>
      <div class="info-card"><span class="info-number">03</span><strong>Device context</strong><span>Browser, operating system, device type, and keyboard type used for each session.</span></div>
      <div class="info-card"><span class="info-number">04</span><strong>Pseudonymous identity</strong><span>No name, email, precise address, password, or exact device location is required.</span></div>
    </div>

    <div class="notice info"><strong>Data privacy and anonymity.</strong> You will be assigned a random <strong>DNA-XXXXX</strong> Participant ID. Your study records will be linked to that code rather than your name. This is an exploratory work in our cybersecurity course. Hence, all collected information shall be used for the sole purpose of this study and will be treated with the highest form of confidentiality. Questions or withdrawal requests may be directed to ${escapeHtml(state.config.study_contact)}.</div>

    <div class="path-choice" role="radiogroup" aria-label="Participation type">
      <label class="choice-card">
        <input type="radio" name="participantPath" value="new" checked>
        <strong>I am a new participant</strong>
        <span>Register once and receive a Participant ID.</span>
      </label>
      <label class="choice-card">
        <input type="radio" name="participantPath" value="returning">
        <strong>I am returning</strong>
        <span>Restore an existing Participant ID on this browser.</span>
      </label>
    </div>

    <label id="consentBox" class="consent-box">
      <input id="consent" type="checkbox">
      <span>I am at least 18 years old, I have read the information above, and I voluntarily consent to the collection and use of the described data for this research study.</span>
    </label>
  `, `<span class="muted">Consent version ${escapeHtml(state.config.consent_version)}</span><button id="homeContinue" class="btn primary" type="button">Continue</button>`);

  const pathInputs = [...document.querySelectorAll('input[name="participantPath"]')];
  const consentBox = document.getElementById('consentBox');
  pathInputs.forEach(input => input.addEventListener('change', () => {
    consentBox.classList.toggle('hidden', input.value === 'returning' && input.checked);
  }));

  document.getElementById('homeContinue').onclick = async () => {
    const path = document.querySelector('input[name="participantPath"]:checked')?.value;
    if (path === 'returning') return restorePage();
    if (!document.getElementById('consent').checked) return showError('Please confirm your consent before continuing.');

    const button = document.getElementById('homeContinue');
    button.disabled = true;
    try {
      const reserved = await api('/api/participants/reserve', {
        method: 'POST',
        body: JSON.stringify({consent_accepted: true, device: detectDevice()}),
      }, false);
      state.token = reserved.participant_token;
      state.recoveryPin = reserved.recovery_pin;
      state.activeSession = reserved.session;
      state.me = {
        participant: {participant_code: reserved.participant_code, profile_completed: false},
        sessions: [reserved.session],
        completed_sessions: 0,
        target_sessions: state.config.target_sessions,
      };
      localStorage.setItem('bd_participant_token', state.token);
      localStorage.setItem('bd_recovery_pin', state.recoveryPin);
      updateParticipantBadge();
      registrationPage();
    } catch (error) {
      button.disabled = false;
      showError(error.message);
    }
  };
}

function restorePage() {
  setProgress(1, 'Restore participant');
  participantBadge.hidden = true;
  screen(`
    <div class="eyebrow">Returning participant</div>
    <h1>Restore your study progress.</h1>
    <p class="lead">Enter the Participant ID and six-digit recovery PIN issued during your first session. After restoration, this browser will remember the participant automatically.</p>
    <div class="form-grid">
      <div class="field full">
        <label for="restoreCode">Participant ID</label>
        <input id="restoreCode" autocomplete="off" autocapitalize="characters" placeholder="DNA-XXXXX" maxlength="9">
      </div>
      <div class="field full">
        <label for="restorePin">Recovery PIN</label>
        <input id="restorePin" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="6 digits">
      </div>
    </div>
    <div class="notice">The recovery PIN is used only to reconnect this browser with the pseudonymous participant record.</div>
  `, `<button id="restoreBack" class="btn text" type="button">Return to study information</button><button id="restoreContinue" class="btn primary" type="button">Continue</button>`);

  document.getElementById('restoreBack').onclick = homePage;
  document.getElementById('restoreContinue').onclick = async () => {
    const code = document.getElementById('restoreCode').value.trim().toUpperCase();
    const pin = document.getElementById('restorePin').value.trim();
    if (!/^DNA-[A-Z0-9]{5}$/.test(code) || !/^\d{6}$/.test(pin)) return showError('Enter a valid DNA-XXXXX Participant ID and six-digit recovery PIN.');
    const button = document.getElementById('restoreContinue');
    button.disabled = true;
    try {
      const result = await api('/api/participants/restore', {
        method: 'POST',
        body: JSON.stringify({participant_code: code, recovery_pin: pin, device: detectDevice()}),
      }, false);
      state.token = result.participant_token;
      state.recoveryPin = pin;
      state.me = result;
      state.activeSession = result.active_session;
      localStorage.setItem('bd_participant_token', state.token);
      localStorage.setItem('bd_recovery_pin', state.recoveryPin);
      updateParticipantBadge();
      returningPage();
    } catch (error) {
      button.disabled = false;
      showError(error.message);
    }
  };
}

function registrationPage() {
  setProgress(2, 'Participant registration');
  updateParticipantBadge();
  const code = state.me?.participant?.participant_code || '';
  screen(`
    <div class="eyebrow">First visit only</div>
    <h1>Create your pseudonymous participant profile.</h1>
    <p class="lead">The information below is collected once. Your typing activity in the text-entry fields also forms the Session 1 <strong>Initial</strong> keystroke sample.</p>

    <div class="identity-panel">
      <div class="identity-item"><span>Participant ID</span><strong>${escapeHtml(code)}</strong></div>
      <div class="identity-item"><span>Recovery PIN</span><strong>${escapeHtml(state.recoveryPin || 'Not available')}</strong></div>
    </div>
    <div class="notice warning"><strong>Save or screenshot both codes.</strong> You will need them only when browser recognition is unavailable or when using another device.</div>

    <form id="registrationForm" class="form-grid" novalidate>
      <div class="field">
        <label for="age">Age</label>
        <input id="age" name="age" type="number" min="18" max="100" required inputmode="numeric">
      </div>
      <div class="field">
        <label for="gender">Gender</label>
        <select id="gender" name="gender" required>
          <option value="">Select one</option>
          <option>Female</option><option>Male</option><option>Non-binary</option><option>Prefer to self-describe</option><option>Prefer not to say</option>
        </select>
      </div>
      <div class="field full">
        <label for="occupation">Profession or job</label>
        <input id="occupation" name="occupation" required autocomplete="organization-title" placeholder="Example: Teacher, accountant, student">
      </div>
      <div class="field">
        <label for="city">City or municipality</label>
        <input id="city" name="city" required autocomplete="address-level2">
      </div>
      <div class="field">
        <label for="province">Province or state</label>
        <input id="province" name="province" required autocomplete="address-level1">
      </div>
      <div class="field full">
        <label for="education">Educational attainment</label>
        <select id="education" name="education" required>
          <option value="">Select one</option>
          <option>Elementary level or graduate</option>
          <option>Junior high school level or graduate</option>
          <option>Senior high school level or graduate</option>
          <option>Technical or vocational certificate</option>
          <option>College or university level</option>
          <option>Bachelor's degree</option>
          <option>Postgraduate diploma or certificate</option>
          <option>Master's degree</option>
          <option>Doctoral degree</option>
          <option>Other</option>
        </select>
      </div>
    </form>
  `, `<span class="muted">Participant information is collected once.</span><button id="registrationContinue" class="btn primary" type="button">Continue</button>`);

  const form = document.getElementById('registrationForm');
  const recorder = createRecorder(form, false);
  document.getElementById('registrationContinue').onclick = () => {
    if (!form.reportValidity()) return showError('Complete all required participant information before continuing.');
    recorder.stop();
    state.initialEvents = recorder.events;
    state.profileDraft = {
      age: Number(document.getElementById('age').value),
      gender: document.getElementById('gender').value,
      occupation: document.getElementById('occupation').value.trim(),
      city: document.getElementById('city').value.trim(),
      province: document.getElementById('province').value.trim(),
      education: document.getElementById('education').value,
    };
    devicePage(true);
  };
}

function devicePage(firstRegistration = false) {
  setProgress(3, 'System and device');
  updateParticipantBadge();
  const detected = detectDevice();
  const previousKeyboard = latestKeyboard();
  const currentDevice = state.device || detected;
  const keyboardOptions = [
    'Laptop built-in keyboard', 'Desktop external keyboard', 'Mechanical keyboard', 'Membrane keyboard',
    'Wireless keyboard', 'Bluetooth keyboard', 'Tablet keyboard cover', 'On-screen or virtual keyboard', 'Other',
  ];

  screen(`
    <div class="eyebrow">Session context</div>
    <div class="session-head">
      <div><h1>Confirm the equipment used today.</h1><p class="lead">Browser and operating system are detected automatically. Select the actual device and keyboard used for this typing session.</p></div>
      <span class="session-tag">Session ${escapeHtml(state.activeSession?.session_number || (state.me?.completed_sessions || 0) + 1)}</span>
    </div>

    <div class="form-grid">
      <div class="field"><label for="browser">Browser</label><input id="browser" value="${escapeHtml(detected.browser)}" readonly></div>
      <div class="field"><label for="os">Operating system</label><input id="os" value="${escapeHtml(detected.os)}" readonly></div>
      <div class="field">
        <label for="deviceType">Device type</label>
        <select id="deviceType">
          <option ${selectedOption('Desktop or laptop', currentDevice.device_type)}>Desktop or laptop</option>
          <option ${selectedOption('Tablet', currentDevice.device_type)}>Tablet</option>
          <option ${selectedOption('Mobile phone', currentDevice.device_type)}>Mobile phone</option>
          <option ${selectedOption('Other', currentDevice.device_type)}>Other</option>
        </select>
      </div>
      <div class="field">
        <label for="keyboardType">Keyboard type</label>
        <select id="keyboardType" required>
          <option value="">Select one</option>
          ${keyboardOptions.map(value => `<option ${selectedOption(value, previousKeyboard || currentDevice.keyboard_type)}>${escapeHtml(value)}</option>`).join('')}
        </select>
        ${previousKeyboard ? `<small>Previously used: ${escapeHtml(previousKeyboard)}. Change it when using a different keyboard.</small>` : '<small>Browsers cannot reliably detect the keyboard model.</small>'}
      </div>
    </div>
    <div class="notice info"><strong>Why this matters:</strong> a different keyboard or device can influence hold time, flight time, typing speed, errors, and pause behavior. Equipment is recorded separately for each session.</div>
  `, `<span class="muted">No software installation is required.</span><button id="deviceContinue" class="btn primary" type="button">Continue</button>`);

  document.getElementById('deviceContinue').onclick = async () => {
    const keyboard = document.getElementById('keyboardType').value;
    if (!keyboard) return showError('Select the keyboard used for this session.');
    state.device = {
      browser: detected.browser,
      os: detected.os,
      device_type: document.getElementById('deviceType').value,
      keyboard_type: keyboard,
    };
    const button = document.getElementById('deviceContinue');
    button.disabled = true;
    try {
      if (firstRegistration) {
        state.profileDraft.device = state.device;
        state.me = await api('/api/participants/register', {
          method: 'POST', body: JSON.stringify(state.profileDraft),
        });
        state.activeSession = state.me.active_session;
      } else if (!state.activeSession) {
        state.activeSession = await api('/api/participants/sessions/start', {
          method: 'POST', body: JSON.stringify({device: state.device}),
        });
      }
      updateParticipantBadge();
      fixedPage();
    } catch (error) {
      button.disabled = false;
      showError(error.message);
    }
  };
}

function normalizeText(value) {
  return String(value || '').replace(/\r\n/g, '\n').trim();
}

function fixedComparison(targetValue, typedValue) {
  const target = normalizeText(targetValue);
  const typed = normalizeText(typedValue);
  let index = 0;
  const sharedLength = Math.min(target.length, typed.length);
  while (index < sharedLength && target[index] === typed[index]) index += 1;

  if (index === target.length && index === typed.length) {
    return {status: 'exact', index, target, typed};
  }
  if (index === typed.length && typed.length < target.length) {
    return {status: 'incomplete', index, target, typed};
  }
  if (index === target.length && typed.length > target.length) {
    return {status: 'extra', index, target, typed};
  }
  return {status: 'mismatch', index, target, typed};
}

function fixedWordBounds(target, index) {
  if (!target.length) return {start: 0, end: 0};
  const safeIndex = Math.max(0, Math.min(index, target.length - 1));
  if (/\s/.test(target[safeIndex])) return {start: safeIndex, end: safeIndex + 1};
  let start = safeIndex;
  let end = safeIndex + 1;
  while (start > 0 && !/\s/.test(target[start - 1])) start -= 1;
  while (end < target.length && !/\s/.test(target[end])) end += 1;
  return {start, end};
}

function visibleCharacter(value) {
  if (value === undefined) return 'end of passage';
  if (value === ' ') return 'a space';
  if (value === '\n') return 'a line break';
  return `“${value}”`;
}

function updateFixedComparison(target, typed, prompt, feedback, finishButton, reviewButton) {
  const comparison = fixedComparison(target, typed);
  const normalizedTarget = comparison.target;
  const normalizedTyped = comparison.typed;
  prompt.classList.remove('exact');
  feedback.className = 'match-feedback';
  reviewButton.dataset.differenceIndex = String(comparison.index);

  if (comparison.status === 'exact') {
    prompt.innerHTML = `<span class="fixed-match-correct">${escapeHtml(normalizedTarget)}</span>`;
    prompt.classList.add('exact');
    feedback.classList.add('exact');
    feedback.innerHTML = '<strong>Exact match.</strong> Select Finished Typing when you are ready.';
    finishButton.disabled = false;
    reviewButton.hidden = true;
    return comparison;
  }

  finishButton.disabled = true;
  if (comparison.status === 'incomplete') {
    prompt.innerHTML = `<span class="fixed-match-correct">${escapeHtml(normalizedTarget.slice(0, comparison.index))}</span><span class="fixed-match-pending">${escapeHtml(normalizedTarget.slice(comparison.index))}</span>`;
    feedback.classList.add('incomplete');
    feedback.innerHTML = `<strong>Correct so far.</strong> ${normalizedTarget.length - normalizedTyped.length} characters remain.`;
    reviewButton.hidden = true;
    return comparison;
  }

  if (comparison.status === 'extra') {
    prompt.innerHTML = `<span class="fixed-match-correct">${escapeHtml(normalizedTarget)}</span>`;
    feedback.classList.add('mismatch');
    feedback.innerHTML = `<strong>Extra text detected.</strong> Remove ${normalizedTyped.length - normalizedTarget.length} character${normalizedTyped.length - normalizedTarget.length === 1 ? '' : 's'} after the end of the passage.`;
    reviewButton.hidden = false;
    return comparison;
  }

  const bounds = fixedWordBounds(normalizedTarget, comparison.index);
  prompt.innerHTML = `<span class="fixed-match-correct">${escapeHtml(normalizedTarget.slice(0, bounds.start))}</span><mark class="fixed-match-error">${escapeHtml(normalizedTarget.slice(bounds.start, bounds.end))}</mark><span class="fixed-match-pending">${escapeHtml(normalizedTarget.slice(bounds.end))}</span>`;
  feedback.classList.add('mismatch');
  feedback.innerHTML = `<strong>First difference at character ${comparison.index + 1}.</strong> Expected ${escapeHtml(visibleCharacter(normalizedTarget[comparison.index]))}, but found ${escapeHtml(visibleCharacter(normalizedTyped[comparison.index]))}. The affected reference word is highlighted.`;
  reviewButton.hidden = false;
  return comparison;
}

function fixedPage() {
  setProgress(4, 'Fixed text typing');
  updateParticipantBadge();
  const target = state.config.fixed_text;
  screen(`
    <div class="eyebrow">Typing activity 1 of 2</div>
    <div class="session-head">
      <div><h1>Type the passage exactly as shown.</h1><p class="lead">Select <strong>Start Typing</strong>, type naturally, correct errors when needed, and select <strong>Finished Typing</strong> only when the passage matches.</p></div>
      <span class="session-tag">Session ${escapeHtml(state.activeSession?.session_number || '')}</span>
    </div>

    <div id="fixedPrompt" class="prompt-card fixed-reference" aria-label="Fixed text prompt"></div>
    <div id="fixedMatchFeedback" class="match-feedback incomplete" aria-live="polite"><strong>Ready.</strong> The reference passage will highlight your progress as you type.</div>

    <div id="fixedCapture" class="capture-panel">
      <div class="capture-toolbar">
        <div class="capture-status"><span id="fixedDot" class="capture-dot"></span><span data-capture-message>Select “Start Typing” when ready.</span></div>
        <div class="capture-buttons">
          <button id="startFixed" class="btn secondary" type="button">Start Typing</button>
          <button id="reviewFixed" class="btn text" type="button" hidden>Pause &amp; Review Difference</button>
          <button id="finishFixed" class="btn outline" type="button" disabled>Finished Typing</button>
        </div>
      </div>
      <textarea id="fixedText" name="fixed_text" disabled spellcheck="false" autocomplete="off" autocorrect="off" autocapitalize="off" aria-label="Type the fixed passage here"></textarea>
      <div class="counter-row"><span id="fixedCount">0 of ${target.length} characters</span></div>
    </div>
  `, `<span class="muted">Copy and paste is disabled.</span><button id="fixedContinue" class="btn primary" type="button" disabled>Continue</button>`);

  const root = document.getElementById('fixedCapture');
  const area = document.getElementById('fixedText');
  const prompt = document.getElementById('fixedPrompt');
  const feedback = document.getElementById('fixedMatchFeedback');
  const startButton = document.getElementById('startFixed');
  const reviewButton = document.getElementById('reviewFixed');
  const finishButton = document.getElementById('finishFixed');
  const continueButton = document.getElementById('fixedContinue');
  const dot = document.getElementById('fixedDot');
  const message = root.querySelector('[data-capture-message]');
  const count = document.getElementById('fixedCount');
  let recorder = null;
  let captureActive = false;
  let capturePhase = 0;
  const eventBuffer = [];
  let latestComparison = updateFixedComparison(target, '', prompt, feedback, finishButton, reviewButton);

  const stopCapture = () => {
    if (!recorder) return;
    recorder.stop();
    eventBuffer.push(...recorder.events);
    recorder = null;
    captureActive = false;
    dot.classList.remove('active');
  };

  const startCapture = () => {
    recorder = createRecorder(root, true, {
      activityType: 'fixed',
      segment: `fixed:${state.activeSession?.id || 'session'}:phase-${capturePhase++}`,
    });
    captureActive = true;
    area.disabled = false;
    dot.classList.add('active');
    reviewButton.textContent = 'Pause & Review Difference';
    if (latestComparison.status === 'mismatch' || latestComparison.status === 'extra') {
      const location = Math.min(Number(reviewButton.dataset.differenceIndex || 0), area.value.length);
      area.focus();
      area.setSelectionRange(location, Math.min(location + 1, area.value.length));
    } else {
      area.focus();
    }
  };

  area.addEventListener('input', () => {
    count.textContent = `${area.value.length} of ${target.length} characters`;
    latestComparison = updateFixedComparison(target, area.value, prompt, feedback, finishButton, reviewButton);
    if (!captureActive && !reviewButton.hidden) reviewButton.textContent = 'Resume Corrections';
  });

  startButton.onclick = () => {
    startCapture();
    startButton.disabled = true;
    finishButton.disabled = latestComparison.status !== 'exact';
    message.textContent = 'Keystroke capture is active. The reference passage updates as you type.';
  };

  reviewButton.onclick = () => {
    if (captureActive) {
      stopCapture();
      area.disabled = true;
      reviewButton.textContent = 'Resume Corrections';
      message.textContent = 'Capture is paused. Review the highlighted difference, then resume corrections.';
      return;
    }
    startCapture();
    message.textContent = 'Correction capture is active in a new timing segment.';
  };

  finishButton.onclick = () => {
    latestComparison = updateFixedComparison(target, area.value, prompt, feedback, finishButton, reviewButton);
    if (latestComparison.status !== 'exact') return;
    stopCapture();
    state.fixedEvents = eventBuffer;
    state.fixedText = area.value;
    area.disabled = true;
    reviewButton.hidden = true;
    finishButton.disabled = true;
    continueButton.disabled = false;
    dot.classList.remove('active');
    message.textContent = 'Fixed-text typing was captured successfully.';
  };

  continueButton.onclick = freePage;
}

function countWords(value) {
  return value.trim().split(/\s+/).filter(Boolean).length;
}

function countSentences(value) {
  const matches = value.trim().match(/[^.!?]+[.!?]+(?:\s|$)/g);
  return matches ? matches.length : 0;
}

function freePage() {
  setProgress(5, 'Free text typing');
  updateParticipantBadge();
  screen(`
    <div class="eyebrow">Typing activity 2 of 2</div>
    <div class="session-head">
      <div><h1>Respond naturally in your own words.</h1><p class="lead">Complete both prompts without copying text from another source. Do not include private, financial, medical, account, or password information.</p></div>
      <span class="session-tag">Session ${escapeHtml(state.activeSession?.session_number || '')}</span>
    </div>

    <div id="freeCapture" class="capture-panel">
      <div class="capture-toolbar">
        <div class="capture-status"><span id="freeDot" class="capture-dot"></span><span data-capture-message>Select “Start Typing” when ready.</span></div>
        <div class="capture-buttons">
          <button id="startFree" class="btn secondary" type="button">Start Typing</button>
          <button id="finishFree" class="btn outline" type="button" disabled>Finished Typing</button>
        </div>
      </div>

      <div class="prompt-group">
        <label for="freeText1">${escapeHtml(state.config.free_prompt_1)}</label>
        <textarea id="freeText1" name="free_text_1" disabled spellcheck="true" autocomplete="off"></textarea>
        <div class="counter-row"><span id="freeCount1">0 words · 0 sentences</span></div>
      </div>
      <div class="prompt-group">
        <label for="freeText2">${escapeHtml(state.config.free_prompt_2)}</label>
        <textarea id="freeText2" name="free_text_2" disabled spellcheck="true" autocomplete="off"></textarea>
        <div class="counter-row"><span id="freeCount2">0 words · 0 sentences</span></div>
      </div>
    </div>
  `, `<span class="muted">Both responses are included in the Free Text metrics.</span><button id="freeContinue" class="btn primary" type="button" disabled>Continue</button>`);

  const root = document.getElementById('freeCapture');
  const first = document.getElementById('freeText1');
  const second = document.getElementById('freeText2');
  const startButton = document.getElementById('startFree');
  const finishButton = document.getElementById('finishFree');
  const continueButton = document.getElementById('freeContinue');
  const dot = document.getElementById('freeDot');
  const message = root.querySelector('[data-capture-message]');
  let recorder = null;

  const updateCounts = () => {
    document.getElementById('freeCount1').textContent = `${countWords(first.value)} words · ${countSentences(first.value)} sentences`;
    document.getElementById('freeCount2').textContent = `${countWords(second.value)} words · ${countSentences(second.value)} sentences`;
  };
  first.addEventListener('input', updateCounts);
  second.addEventListener('input', updateCounts);

  startButton.onclick = () => {
    recorder = createRecorder(root, true);
    first.disabled = false;
    second.disabled = false;
    first.focus();
    startButton.disabled = true;
    finishButton.disabled = false;
    dot.classList.add('active');
    message.textContent = 'Keystroke capture is active for both responses.';
  };

  finishButton.onclick = () => {
    const firstWords = countWords(first.value);
    const firstSentences = countSentences(first.value);
    const secondWords = countWords(second.value);
    const secondSentences = countSentences(second.value);
    if (firstWords < 5 || firstSentences < 1) return showError('The first response must be one complete sentence with at least five words.');
    if (secondWords < 15 || secondSentences < 2 || secondSentences > 3) return showError('The second response must contain 2–3 complete sentences and at least 15 words.');

    recorder?.stop();
    state.freeEvents = recorder?.events || [];
    state.freeText1 = first.value.trim();
    state.freeText2 = second.value.trim();
    first.disabled = true;
    second.disabled = true;
    finishButton.disabled = true;
    continueButton.disabled = false;
    dot.classList.remove('active');
    message.textContent = 'Free-text typing was captured successfully.';
  };

  continueButton.onclick = analyzeAndShowResults;
}

async function analyzeAndShowResults() {
  setProgress(6, 'Session results');
  showLoading('Calculating the eight keystroke metrics…');
  try {
    const profile = state.me?.participant || state.profileDraft || {};
    const initialText = [profile.age, profile.gender, profile.occupation, profile.city, profile.province, profile.education].filter(Boolean).join(' ');
    state.analysis = await api(`/api/participants/sessions/${state.activeSession.id}/analyze`, {
      method: 'POST',
      body: JSON.stringify({
        device: state.device,
        initial_text: initialText,
        fixed_text: state.fixedText,
        free_text_1: state.freeText1,
        free_text_2: state.freeText2,
        initial_events: state.initialEvents,
        fixed_events: state.fixedEvents,
        free_events: state.freeEvents,
      }),
    });
    state.activeSession = state.analysis.session;
    resultsPage();
  } catch (error) {
    screen(`
      <div class="eyebrow">Analysis interrupted</div>
      <h1>The session could not be analyzed.</h1>
      <div class="error-banner">${escapeHtml(error.message)}</div>
      <p class="lead">Your current typing responses remain on this device only until the page is replaced. Return to the free-text activity and complete it again.</p>
    `, `<button id="retryAnalysis" class="btn primary" type="button">Continue</button>`, 'end');
    document.getElementById('retryAnalysis').onclick = freePage;
  }
}

function metricValue(metric, value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return 'Not available';
  const units = {
    hold_time: ' ms', flight_time: ' ms', digraph_latency: ' ms', trigraph_latency: ' ms',
    typing_speed: ' WPM', error_rate: '%', pause_pattern: ' ms', consistency_score: ' / 100',
  };
  return `${Number(value).toFixed(2)}${units[metric] || ''}`;
}

function metricScopeCard(scope, values) {
  const [title, subtitle] = SCOPE_COPY[scope];
  const metrics = state.config.metrics.map(metric => `
    <li><span>${escapeHtml(state.config.metric_labels[metric])}</span><strong>${escapeHtml(metricValue(metric, values?.[metric]))}</strong></li>`).join('');
  return `<article class="metric-scope"><header><strong>${escapeHtml(title)}</strong><span>${escapeHtml(subtitle)}</span></header><ul class="metric-list">${metrics}</ul></article>`;
}

function resultsPage() {
  setProgress(6, 'Session results');
  updateParticipantBadge();
  const metrics = state.analysis?.metrics || {};
  const warnings = state.analysis?.quality?.warnings || [];
  screen(`
    <div class="eyebrow">Review before submission</div>
    <h1>Your eight keystroke metrics are ready.</h1>
    <p class="lead">These are descriptive research measurements for the current session. They are not a diagnosis, identity determination, or final authentication decision.</p>

    <div class="metrics-intro">
      <h2>Session ${escapeHtml(state.activeSession?.session_number || '')} metric vectors</h2>
      <span class="session-tag">Not yet submitted</span>
    </div>
    <div class="metrics-scopes">
      ${metricScopeCard('initial', metrics.initial)}
      ${metricScopeCard('fixed', metrics.fixed)}
      ${metricScopeCard('free', metrics.free)}
      ${metricScopeCard('combined', metrics.combined)}
    </div>
    <div class="notice info"><strong>Scope interpretation:</strong> Initial uses first-time registration keystrokes; Fixed uses the standard passage; Free combines both free-text responses; Combined uses Fixed + Free so all longitudinal sessions remain comparable.</div>
    ${warnings.length ? `<div class="notice warning"><strong>Data-quality notes</strong><br>${warnings.map(escapeHtml).join('<br>')}</div>` : ''}
  `, `<span class="muted">Select Submit to permanently record this session.</span><button id="submitSession" class="btn primary" type="button">Submit</button>`);

  document.getElementById('submitSession').onclick = submitSession;
}

async function submitSession() {
  const button = document.getElementById('submitSession');
  button.disabled = true;
  try {
    state.me = await api(`/api/participants/sessions/${state.activeSession.id}/submit`, {method: 'POST'});
    state.activeSession = null;
    resetCaptureState(true);
    updateParticipantBadge();
    thankYouPage();
  } catch (error) {
    button.disabled = false;
    showError(error.message);
  }
}

function sessionRows(sessions, limit = 10) {
  const rows = sessions.slice(-limit).reverse();
  if (!rows.length) return '<tr><td colspan="3">No completed sessions yet.</td></tr>';
  return rows.map(session => `
    <tr>
      <td>Session ${escapeHtml(session.session_number)}</td>
      <td><span class="status-pill">Completed</span></td>
      <td>${session.completed_at ? escapeHtml(new Date(session.completed_at).toLocaleString()) : '—'}</td>
    </tr>`).join('');
}

function thankYouPage() {
  setProgress(7, 'Confirmation');
  updateParticipantBadge();
  const participant = state.me.participant;
  const complete = state.me.study_complete;
  const pct = Math.min(100, Math.round((state.me.completed_sessions / state.me.target_sessions) * 100));
  screen(`
    <div class="eyebrow">Session submitted</div>
    <h1>${complete ? 'You reached the study target. Thank you.' : 'Thank you. Your typing session is recorded.'}</h1>
    <div class="notice success"><strong>Confirmation:</strong> Session ${escapeHtml(state.me.completed_sessions)} of ${escapeHtml(state.me.target_sessions)} was submitted successfully.</div>

    <div class="progress-summary">
      <div class="progress-ring" style="--pct:${pct}"><div><strong>${escapeHtml(state.me.completed_sessions)}/${escapeHtml(state.me.target_sessions)}</strong><span>sessions complete</span></div></div>
      <div>
        <h2>Keep your study identity</h2>
        <p>This browser will normally recognize you automatically. Save the Participant ID and recovery PIN in case you return from another browser or device.</p>
        <div class="identity-panel">
          <div class="identity-item"><span>Participant ID</span><strong>${escapeHtml(participant.participant_code)}</strong></div>
          <div class="identity-item"><span>Recovery PIN</span><strong>${escapeHtml(state.recoveryPin || 'Previously issued')}</strong></div>
        </div>
      </div>
    </div>

    ${complete ? '<div class="notice info">No additional sessions are required. Keep this confirmation for your records.</div>' : '<div class="notice info"><strong>Longitudinal reminder:</strong> Completing sessions on multiple days provides stronger evidence of natural behavioral variation than completing all sessions at once.</div>'}
  `, complete ? '' : `<span class="muted">You may continue now or return on another day.</span><button id="anotherSession" class="btn primary" type="button">Do Another Typing Session</button>`);

  if (!complete) document.getElementById('anotherSession').onclick = returningPage;
}

function returningPage() {
  setProgress(1, 'Participant check-in');
  updateParticipantBadge();
  if (!state.me) return loadCurrentParticipant();
  const participant = state.me.participant;
  const sessions = completedSessions();
  const pct = Math.min(100, Math.round((state.me.completed_sessions / state.me.target_sessions) * 100));
  const activeLabel = state.activeSession ? `Session ${state.activeSession.session_number} is ready to resume.` : `Your next activity will be Session ${state.me.completed_sessions + 1}.`;

  screen(`
    <div class="eyebrow">Welcome back</div>
    <h1>Continue as ${escapeHtml(participant.participant_code)}?</h1>
    <p class="lead">Confirm that you are the participant shown above. Your registration information is remembered and will not be requested again.</p>

    <div class="progress-summary">
      <div class="progress-ring" style="--pct:${pct}"><div><strong>${escapeHtml(state.me.completed_sessions)}/${escapeHtml(state.me.target_sessions)}</strong><span>sessions complete</span></div></div>
      <div>
        <h2>${escapeHtml(activeLabel)}</h2>
        <p>${state.me.study_complete ? 'The required study target has been completed.' : 'The next session includes device confirmation, fixed-text typing, free-text typing, metric review, and submission.'}</p>
      </div>
    </div>

    <h2>Previous typing sessions</h2>
    <div class="session-table-wrap">
      <table class="session-table">
        <thead><tr><th>Activity</th><th>Status</th><th>Date and time</th></tr></thead>
        <tbody>${sessionRows(sessions)}</tbody>
      </table>
    </div>
  `, `<button id="notMe" class="btn text" type="button">This is not me</button>${state.me.study_complete ? '' : '<button id="returnContinue" class="btn primary" type="button">Continue</button>'}`);

  document.getElementById('notMe').onclick = () => {
    localStorage.removeItem('bd_participant_token');
    localStorage.removeItem('bd_recovery_pin');
    state.token = '';
    state.recoveryPin = '';
    state.me = null;
    state.activeSession = null;
    participantBadge.hidden = true;
    homePage();
  };

  if (!state.me.study_complete) document.getElementById('returnContinue').onclick = async () => {
    resetCaptureState(true);
    state.activeSession = state.me.active_session;
    if (state.activeSession?.status === 'analyzed') {
      try {
        const result = await api(`/api/participants/sessions/${state.activeSession.id}/metrics`);
        state.analysis = {session: state.activeSession, ...result};
        return resultsPage();
      } catch (error) {
        return showError(error.message);
      }
    }
    devicePage(false);
  };
}

async function loadCurrentParticipant() {
  showLoading('Recognizing this participant…');
  try {
    state.me = await api('/api/participants/me');
    state.activeSession = state.me.active_session;
    updateParticipantBadge();
    if (!state.me.participant.profile_completed) return registrationPage();
    if (state.activeSession?.status === 'analyzed') {
      const result = await api(`/api/participants/sessions/${state.activeSession.id}/metrics`);
      state.analysis = {session: state.activeSession, ...result};
      return resultsPage();
    }
    returningPage();
  } catch (_error) {
    localStorage.removeItem('bd_participant_token');
    localStorage.removeItem('bd_recovery_pin');
    state.token = '';
    state.recoveryPin = '';
    state.me = null;
    state.activeSession = null;
    participantBadge.hidden = true;
    homePage();
  }
}

async function initialize() {
  try {
    state.config = await api('/api/public/config', {}, false);
    document.title = `${state.config.app_name} — Participant Study`;
    if (state.token) await loadCurrentParticipant();
    else homePage();
  } catch (error) {
    setProgress(0, 'Service unavailable');
    screen(`<div class="eyebrow">Service unavailable</div><h1>The study interface could not be loaded.</h1><div class="error-banner">${escapeHtml(error.message)}</div>`);
  }
}

document.addEventListener('DOMContentLoaded', initialize);
