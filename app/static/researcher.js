const root = document.getElementById('researchApp');
const researchState = {participants: [], sessions: [], baselines: [], runs: [], dashboard: null};

function esc(value) {
  return String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
}
function pct(value) { return value === null || value === undefined ? '—' : `${(Number(value) * 100).toFixed(2)}%`; }
function number(value, digits = 2) { return value === null || value === undefined ? '—' : Number(value).toFixed(digits); }

async function rapi(path, options = {}) {
  const response = await fetch(path, {credentials: 'same-origin', headers: {'Content-Type': 'application/json', ...(options.headers || {})}, ...options});
  const type = response.headers.get('content-type') || '';
  const data = type.includes('application/json') ? await response.json() : await response.text();
  if (!response.ok) throw new Error(data?.detail || data || 'Request failed');
  return data;
}

function loginView(message = '') {
  root.innerHTML = `<div class="login-wrap"><form id="loginForm" class="login-card">
    <div class="dna-mark">BD</div>
    <div class="page-kicker">Researcher access</div>
    <h1>Behavioral DNA Console</h1>
    <p class="muted">Enter the researcher password configured on the deployment server.</p>
    ${message ? `<div class="error-banner">${esc(message)}</div>` : ''}
    <div class="field"><label for="password">Researcher password</label><input id="password" type="password" autocomplete="current-password" required></div>
    <div class="action-row end"><button class="btn primary" type="submit">Sign in</button></div>
  </form></div>`;
  document.getElementById('loginForm').onsubmit = async event => {
    event.preventDefault();
    try {
      await rapi('/api/research/login', {method: 'POST', body: JSON.stringify({password: document.getElementById('password').value})});
      await loadConsole();
    } catch (error) { loginView(error.message); }
  };
}

function consoleShell() {
  root.innerHTML = `<div class="research-layout">
    <aside class="research-sidebar">
      <div class="research-logo"><div class="dna-mark">BD</div><div><strong>Behavioral DNA</strong><span>Researcher Console</span></div></div>
      <nav class="nav-list">
        <button data-view="dashboard" class="active">Dashboard</button>
        <button data-view="participants">Participants & Sessions</button>
        <button data-view="baselines">Baseline Builder</button>
        <button data-view="evaluation">Engine Evaluation</button>
        <button data-view="results">Evaluation Results</button>
        <button data-view="export">Data Export</button>
      </nav>
      <div class="sidebar-bottom"><button id="logout" class="btn ghost" style="width:100%;color:white;border-color:rgba(255,255,255,.3)">Sign out</button></div>
    </aside>
    <main class="research-main">
      <header class="research-topbar"><div><div class="page-kicker">Research administration</div><h1 id="viewTitle">Dashboard</h1></div><button id="refresh" class="btn secondary">Refresh Data</button></header>
      <div id="researchView"></div>
    </main>
  </div>`;
  document.querySelectorAll('[data-view]').forEach(button => button.onclick = () => switchView(button.dataset.view));
  document.getElementById('logout').onclick = async () => { await rapi('/api/research/logout', {method: 'POST'}); loginView(); };
  document.getElementById('refresh').onclick = async () => { await loadData(); const active = document.querySelector('[data-view].active')?.dataset.view || 'dashboard'; renderView(active); };
}

async function loadData() {
  [researchState.dashboard, researchState.participants, researchState.sessions, researchState.baselines, researchState.runs] = await Promise.all([
    rapi('/api/research/dashboard'),
    rapi('/api/research/participants'),
    rapi('/api/research/sessions?status=completed'),
    rapi('/api/research/baselines'),
    rapi('/api/research/evaluations'),
  ]);
}

async function loadConsole() {
  consoleShell();
  await loadData();
  renderDashboard();
}

function switchView(view) {
  document.querySelectorAll('[data-view]').forEach(button => button.classList.toggle('active', button.dataset.view === view));
  const titles = {dashboard:'Dashboard', participants:'Participants & Sessions', baselines:'Baseline Builder', evaluation:'Engine Evaluation', results:'Evaluation Results', export:'Data Export'};
  document.getElementById('viewTitle').textContent = titles[view];
  renderView(view);
}

function renderView(view) {
  if (view === 'dashboard') renderDashboard();
  if (view === 'participants') renderParticipants();
  if (view === 'baselines') renderBaselines();
  if (view === 'evaluation') renderEvaluation();
  if (view === 'results') renderResults();
  if (view === 'export') renderExport();
}

function renderDashboard() {
  const d = researchState.dashboard;
  document.getElementById('researchView').innerHTML = `
    <div class="stat-grid">
      <div class="stat-card"><span>Participants</span><strong>${d.participants}</strong></div>
      <div class="stat-card"><span>Completed sessions</span><strong>${d.completed_sessions}</strong></div>
      <div class="stat-card"><span>Reached ${d.target_sessions} sessions</span><strong>${d.participants_reaching_target}</strong></div>
      <div class="stat-card"><span>Baselines</span><strong>${d.baselines}</strong></div>
      <div class="stat-card"><span>Evaluation runs</span><strong>${d.evaluation_runs}</strong></div>
    </div>
    <section class="research-panel" style="margin-top:18px">
      <h2>Study readiness</h2>
      <p>The platform stores raw telemetry, four activity-specific metric vectors, exact baseline session selections, engine configurations, and evaluation outcomes. Sessions analyzed but not submitted: <strong>${d.analyzed_not_submitted}</strong>.</p>
      <div class="notice">Build baselines only from designated enrollment sessions. Use separate, subject-disjoint or holdout sessions for final evaluation to avoid optimistic performance estimates.</div>
    </section>
    <section class="research-panel"><h2>Participant progress</h2>${participantProgressTable()}</section>`;
}

function participantProgressTable() {
  const rows = researchState.participants.map(p => `<tr><td>${esc(p.participant_code)}</td><td>${esc(p.city)}, ${esc(p.province)}</td><td>${p.completed_sessions} / ${p.target_sessions}</td><td>${p.last_seen_at ? new Date(p.last_seen_at).toLocaleString() : '—'}</td></tr>`).join('');
  return `<div class="table-wrap"><table class="data-table"><thead><tr><th>Participant</th><th>Location</th><th>Progress</th><th>Last seen</th></tr></thead><tbody>${rows || '<tr><td colspan="4">No registered participants yet.</td></tr>'}</tbody></table></div>`;
}

function renderParticipants() {
  const participantRows = researchState.participants.map(p => `<tr><td>${esc(p.participant_code)}</td><td>${p.age}</td><td>${esc(p.gender)}</td><td>${esc(p.occupation)}</td><td>${esc(p.city)}, ${esc(p.province)}</td><td>${esc(p.education)}</td><td>${p.completed_sessions}/${p.target_sessions}</td></tr>`).join('');
  const sessionRows = researchState.sessions.map(s => `<tr><td>${esc(s.session_code)}</td><td>${esc(s.participant_code)}</td><td>${s.session_number}</td><td>${esc(s.browser)}</td><td>${esc(s.os)}</td><td>${esc(s.keyboard_type)}</td><td>${number((s.fixed_match_ratio || 0) * 100)}%</td><td>${s.completed_at ? new Date(s.completed_at).toLocaleString() : '—'}</td><td><button class="inline-link" data-detail="${s.id}">View</button></td></tr>`).join('');
  document.getElementById('researchView').innerHTML = `
    <section class="research-panel"><h2>Participants</h2><div class="table-wrap"><table class="data-table"><thead><tr><th>ID</th><th>Age</th><th>Gender</th><th>Occupation</th><th>Location</th><th>Education</th><th>Sessions</th></tr></thead><tbody>${participantRows || '<tr><td colspan="7">No participants.</td></tr>'}</tbody></table></div></section>
    <section class="research-panel"><h2>Completed typing sessions</h2><div class="table-wrap"><table class="data-table"><thead><tr><th>Session ID</th><th>Participant</th><th>No.</th><th>Browser</th><th>OS</th><th>Keyboard</th><th>Fixed match</th><th>Completed</th><th></th></tr></thead><tbody>${sessionRows || '<tr><td colspan="9">No completed sessions.</td></tr>'}</tbody></table></div></section>
    <section id="sessionDetail" class="research-panel hidden"></section>`;
  document.querySelectorAll('[data-detail]').forEach(button => button.onclick = () => showSessionDetail(Number(button.dataset.detail)));
}

async function showSessionDetail(id) {
  try {
    const data = await rapi(`/api/research/sessions/${id}`);
    const detail = document.getElementById('sessionDetail');
    const metricRows = Object.entries(data.metrics).map(([scope, vector]) => `<tr><td><strong>${esc(scope)}</strong></td><td>${number(vector.hold_time)}</td><td>${number(vector.flight_time)}</td><td>${number(vector.digraph_latency)}</td><td>${number(vector.trigraph_latency)}</td><td>${number(vector.typing_speed)}</td><td>${number(vector.error_rate)}</td><td>${number(vector.pause_pattern)}</td><td>${number(vector.consistency_score)}</td></tr>`).join('');
    detail.classList.remove('hidden');
    detail.innerHTML = `<h2>Session ${esc(data.session.session_code)}</h2><p>${data.raw_event_count.toLocaleString()} raw events. Fixed-text match: ${number((data.session.fixed_match_ratio || 0) * 100)}%.</p><div class="table-wrap"><table class="data-table"><thead><tr><th>Scope</th><th>Hold</th><th>Flight</th><th>Digraph</th><th>Trigraph</th><th>WPM</th><th>Error %</th><th>Pause</th><th>Consistency</th></tr></thead><tbody>${metricRows}</tbody></table></div><div class="notice"><strong>Quality:</strong><pre style="white-space:pre-wrap">${esc(JSON.stringify(data.session.quality, null, 2))}</pre></div>`;
    detail.scrollIntoView({behavior: 'smooth'});
  } catch (error) { alert(error.message); }
}

function participantOptions() {
  return researchState.participants.map(p => `<option value="${p.id}">${esc(p.participant_code)} — ${p.completed_sessions} sessions</option>`).join('');
}
function baselineOptions() {
  return researchState.baselines.map(b => `<option value="${b.id}">${esc(b.name)} (${esc(b.activity_scope)}, ${b.session_ids.length} sessions)</option>`).join('');
}

function renderBaselines() {
  const baselineRows = researchState.baselines.map(b => `<tr><td>${b.id}</td><td>${esc(b.name)}</td><td>${esc(b.participant_code)}</td><td>${esc(b.activity_scope)}</td><td>${b.session_ids.join(', ')}</td><td>${b.baseline?.readiness?.session_count ?? '—'}</td><td>${b.baseline?.readiness?.meets_minimum_for_pilot ? '<span class="status-pill completed">Pilot-ready</span>' : '<span class="status-pill">Limited</span>'}</td></tr>`).join('');
  document.getElementById('researchView').innerHTML = `
    <div class="research-grid">
      <section class="research-panel">
        <h2>1. Select enrollment sessions</h2>
        <div class="form-grid">
          <div class="field full"><label for="baselineParticipant">Participant</label><select id="baselineParticipant">${participantOptions()}</select></div>
          <div class="field"><label for="baselineScope">Metric vector</label><select id="baselineScope"><option value="combined">Combined</option><option value="fixed">Fixed</option><option value="free">Free</option><option value="initial">Initial</option></select></div>
          <div class="field"><label for="baselineName">Baseline name</label><input id="baselineName" placeholder="Optional"></div>
        </div>
        <div id="baselineSessionList" class="checkbox-list" style="margin-top:16px"></div>
        <div class="action-row end"><button id="buildBaseline" class="btn primary">Build Baseline</button></div>
      </section>
      <section class="research-panel">
        <h2>Method</h2>
        <p>The baseline calculates the mean, standard deviation, ±2 SD behavioral envelope, shrunk correlation matrix, and inverse correlation matrix from the exact selected sessions.</p>
        <div class="notice warning">For final reporting, do not reuse baseline-development sessions as test sessions. Preserve the selected session IDs in the manuscript and exported dataset.</div>
      </section>
    </div>
    <section class="research-panel"><h2>Existing baselines</h2><div class="table-wrap"><table class="data-table"><thead><tr><th>ID</th><th>Name</th><th>Participant</th><th>Scope</th><th>Session IDs</th><th>N</th><th>Readiness</th></tr></thead><tbody>${baselineRows || '<tr><td colspan="7">No baselines have been created.</td></tr>'}</tbody></table></div></section>`;
  const select = document.getElementById('baselineParticipant');
  select.onchange = renderBaselineSessionList;
  document.getElementById('baselineScope').onchange = renderBaselineSessionList;
  renderBaselineSessionList();
  document.getElementById('buildBaseline').onclick = buildBaseline;
}

function renderBaselineSessionList() {
  const participantId = Number(document.getElementById('baselineParticipant')?.value);
  const scope = document.getElementById('baselineScope')?.value;
  const rows = researchState.sessions.filter(s => s.participant_id === participantId && s.metrics_available.includes(scope));
  document.getElementById('baselineSessionList').innerHTML = rows.length ? rows.map(s => `<label class="checkbox-item"><input type="checkbox" value="${s.id}"><span><strong>Session ${s.session_number}</strong><br><small>${esc(s.session_code)} · ${s.completed_at ? new Date(s.completed_at).toLocaleString() : ''}</small></span><small>${esc(s.keyboard_type)}</small></label>`).join('') : '<div class="notice">No completed sessions contain this metric vector.</div>';
}

async function buildBaseline() {
  const sessionIds = [...document.querySelectorAll('#baselineSessionList input:checked')].map(input => Number(input.value));
  try {
    const baseline = await rapi('/api/research/baselines', {method:'POST', body: JSON.stringify({
      participant_id: Number(document.getElementById('baselineParticipant').value),
      session_ids: sessionIds,
      activity_scope: document.getElementById('baselineScope').value,
      name: document.getElementById('baselineName').value,
    })});
    alert(`Baseline ${baseline.id} created.`);
    researchState.baselines = await rapi('/api/research/baselines');
    researchState.dashboard = await rapi('/api/research/dashboard');
    renderBaselines();
  } catch (error) { alert(error.message); }
}

function renderEvaluation() {
  document.getElementById('researchView').innerHTML = `
    <section class="research-panel">
      <h2>Evaluation design</h2>
      <div class="form-grid">
        <div class="field full"><label for="evaluationBaseline">Baseline</label><select id="evaluationBaseline">${baselineOptions()}</select></div>
        <div class="field"><label for="evaluationName">Run name</label><input id="evaluationName" placeholder="Holdout evaluation"></div>
        <div class="field"><label for="fusionMethod">Fusion method</label><select id="fusionMethod"><option>median</option><option>mean</option><option>minimum</option><option>weighted</option><option>majority</option></select></div>
      </div>
    </section>
    <div class="research-grid">
      <section class="research-panel"><h2>1. Test sessions and expected labels</h2><div id="evaluationSessionList" class="checkbox-list"></div></section>
      <section class="research-panel">
        <h2>2. Engine configuration</h2>
        <div class="engine-grid">
          ${['z_score','envelope','mahalanobis','drift'].map(engine => `<div class="engine-card"><label><input id="active_${engine}" type="checkbox" checked>${engine.replace('_',' ')}</label><div class="field" style="margin-top:9px"><small>Weight</small><input id="weight_${engine}" type="number" min="0" step="0.1" value="1"></div></div>`).join('')}
        </div>
        <h2>Decision thresholds</h2>
        <div class="form-grid">
          <div class="field"><label>Genuine</label><input id="th_genuine" type="number" value="85"></div>
          <div class="field"><label>Genuine minimum</label><input id="th_genuine_min" type="number" value="70"></div>
          <div class="field"><label>Monitor</label><input id="th_monitor" type="number" value="70"></div>
          <div class="field"><label>Monitor minimum</label><input id="th_monitor_min" type="number" value="45"></div>
          <div class="field"><label>Step-up</label><input id="th_step_up" type="number" value="55"></div>
          <div class="field"><label>Lock override</label><input id="th_lock" type="number" value="25"></div>
          <div class="field"><label>Majority cutoff</label><input id="majority_cutoff" type="number" value="70"></div>
        </div>
      </section>
    </div>
    <div class="action-row end"><button id="runEvaluation" class="btn primary">Run Evaluation</button></div>`;
  document.getElementById('evaluationBaseline').onchange = renderEvaluationSessionList;
  renderEvaluationSessionList();
  document.getElementById('runEvaluation').onclick = runEvaluation;
}

function renderEvaluationSessionList() {
  const baseline = researchState.baselines.find(b => b.id === Number(document.getElementById('evaluationBaseline')?.value));
  const container = document.getElementById('evaluationSessionList');
  if (!baseline) { container.innerHTML = '<div class="notice">Create a baseline first.</div>'; return; }
  const sessions = researchState.sessions.filter(s => s.metrics_available.includes(baseline.activity_scope));
  container.innerHTML = sessions.map(s => {
    const automatic = s.participant_id === baseline.participant_id ? 'genuine' : 'impostor';
    const inBaseline = baseline.session_ids.includes(s.id);
    return `<div class="checkbox-item"><input type="checkbox" value="${s.id}" ${inBaseline ? 'disabled' : ''}><span><strong>${esc(s.participant_code)} · Session ${s.session_number}</strong><br><small>${esc(s.session_code)}${inBaseline ? ' · baseline-development session' : ''}</small></span><select data-label-for="${s.id}" ${inBaseline ? 'disabled' : ''}><option value="auto">Auto: ${automatic}</option><option value="genuine">Genuine</option><option value="impostor">Impostor</option></select></div>`;
  }).join('') || '<div class="notice">No eligible test sessions.</div>';
}

async function runEvaluation() {
  const baseline = researchState.baselines.find(b => b.id === Number(document.getElementById('evaluationBaseline').value));
  if (!baseline) return alert('Create and select a baseline.');
  const checked = [...document.querySelectorAll('#evaluationSessionList input[type="checkbox"]:checked')];
  const sessionIds = checked.map(input => Number(input.value));
  const overrides = {};
  sessionIds.forEach(id => {
    const selected = document.querySelector(`[data-label-for="${id}"]`).value;
    if (selected !== 'auto') overrides[String(id)] = selected;
  });
  const engines = ['z_score','envelope','mahalanobis','drift'];
  const config = {
    active_engines: Object.fromEntries(engines.map(e => [e, document.getElementById(`active_${e}`).checked])),
    fusion_method: document.getElementById('fusionMethod').value,
    majority_cutoff: Number(document.getElementById('majority_cutoff').value),
    weights: Object.fromEntries(engines.map(e => [e, Number(document.getElementById(`weight_${e}`).value)])),
    thresholds: {
      genuine: Number(document.getElementById('th_genuine').value),
      genuine_min: Number(document.getElementById('th_genuine_min').value),
      monitor: Number(document.getElementById('th_monitor').value),
      monitor_min: Number(document.getElementById('th_monitor_min').value),
      step_up: Number(document.getElementById('th_step_up').value),
      lock_override: Number(document.getElementById('th_lock').value),
    },
  };
  try {
    const response = await rapi('/api/research/evaluations', {method:'POST', body: JSON.stringify({
      baseline_id: baseline.id,
      test_session_ids: sessionIds,
      activity_scope: baseline.activity_scope,
      name: document.getElementById('evaluationName').value,
      config,
      label_overrides: overrides,
    })});
    researchState.runs = await rapi('/api/research/evaluations');
    researchState.dashboard = await rapi('/api/research/dashboard');
    switchView('results');
    await showEvaluationRun(response.run.id);
  } catch (error) { alert(error.message); }
}

function renderResults() {
  const rows = researchState.runs.map(run => `<tr><td>${run.id}</td><td>${esc(run.name)}</td><td>${run.baseline_id}</td><td>${esc(run.activity_scope)}</td><td>${run.summary.n}</td><td>${pct(run.summary.accuracy)}</td><td>${pct(run.summary.far_fpr)}</td><td>${pct(run.summary.frr_fnr)}</td><td><button class="inline-link" data-run="${run.id}">Open</button></td></tr>`).join('');
  document.getElementById('researchView').innerHTML = `<section class="research-panel"><h2>Saved evaluation runs</h2><div class="table-wrap"><table class="data-table"><thead><tr><th>ID</th><th>Name</th><th>Baseline</th><th>Scope</th><th>N</th><th>Accuracy</th><th>FAR</th><th>FRR</th><th></th></tr></thead><tbody>${rows || '<tr><td colspan="9">No evaluation runs.</td></tr>'}</tbody></table></div></section><section id="runDetail" class="research-panel hidden"></section>`;
  document.querySelectorAll('[data-run]').forEach(button => button.onclick = () => showEvaluationRun(Number(button.dataset.run)));
}

async function showEvaluationRun(id) {
  try {
    const data = await rapi(`/api/research/evaluations/${id}`);
    const s = data.run.summary;
    const engineHeaders = ['Z-score','Envelope','Mahalanobis','Drift'];
    const resultRows = data.results.map(row => `<tr><td>${esc(row.participant_code)}</td><td>${row.session_number}</td><td>${esc(row.expected_label)}</td>${row.engine_results.map(engine => `<td>${number(engine.confidence)}%</td>`).join('')}<td>${number(row.decision.overall_confidence)}%</td><td>${esc(row.decision.final_action)}</td><td>${esc(row.decision.predicted_label)}</td></tr>`).join('');
    const detail = document.getElementById('runDetail');
    detail.classList.remove('hidden');
    detail.innerHTML = `<h2>${esc(data.run.name)}</h2>
      <p>Fusion: <strong>${esc(data.run.config.fusion_method)}</strong>. Activity scope: <strong>${esc(data.run.activity_scope)}</strong>.</p>
      <div class="confusion-grid"><div class="confusion-cell"><span>TP</span><strong>${s.TP}</strong></div><div class="confusion-cell"><span>TN</span><strong>${s.TN}</strong></div><div class="confusion-cell"><span>FP</span><strong>${s.FP}</strong></div><div class="confusion-cell"><span>FN</span><strong>${s.FN}</strong></div></div>
      <div class="stat-grid" style="margin-top:14px"><div class="stat-card"><span>Accuracy</span><strong>${pct(s.accuracy)}</strong></div><div class="stat-card"><span>Precision</span><strong>${pct(s.precision)}</strong></div><div class="stat-card"><span>Recall</span><strong>${pct(s.recall_tpr)}</strong></div><div class="stat-card"><span>F1</span><strong>${pct(s.f1)}</strong></div><div class="stat-card"><span>AUC / EER</span><strong style="font-size:1.15rem">${number(s.auc,3)} / ${pct(s.eer)}</strong></div></div>
      <div class="table-wrap"><table class="data-table"><thead><tr><th>Participant</th><th>Session</th><th>Expected</th>${engineHeaders.map(h => `<th>${h}</th>`).join('')}<th>Fused</th><th>Action</th><th>Predicted</th></tr></thead><tbody>${resultRows}</tbody></table></div>`;
    detail.scrollIntoView({behavior:'smooth'});
  } catch (error) { alert(error.message); }
}

function renderExport() {
  document.getElementById('researchView').innerHTML = `<section class="research-panel"><h2>Export the research dataset</h2><p>The export ZIP contains UTF-8 CSV files for participants, devices, study sessions, raw keystroke events, metric vectors, baselines, evaluation runs, and per-session engine decisions.</p><div class="notice">Authentication tokens and recovery PIN hashes are excluded. Raw printable key values are also excluded by default unless the deployment explicitly enables them.</div><div class="action-row end"><a class="btn primary" href="/api/research/export" download>Download Data Export</a></div></section>`;
}

async function initializeResearcher() {
  try {
    await rapi('/api/research/me');
    await loadConsole();
  } catch (_error) { loginView(); }
}

document.addEventListener('DOMContentLoaded', initializeResearcher);
