# Participant UI Rebuild — Release 4.2

## Correction history

Release 4.1 replaced the participant-facing layer that remained too close to the interaction style of the supplied prototype. Release 4.2 corrects the fixed-text validation experience identified during participant testing.

## Guided participant experience

The public route has no research menu, engine configuration, baseline controls, database controls, or researcher sections. Participants move through one screen at a time.

### New participant

1. Launch and consent
2. Participant registration
3. System and device confirmation
4. Fixed-text typing
5. Free-text typing
6. Four-scope metric results
7. Submit
8. Confirmation and next-session option

### Returning participant

1. Same-browser recognition or Participant ID recovery
2. Participant confirmation
3. Previous-session history
4. Device and keyboard confirmation
5. Fixed-text typing
6. Free-text typing
7. Metric results
8. Submit and confirmation

## Fixed-text validation enhancement

The reference passage now changes in real time as the participant types:

- correctly matched text is visually confirmed;
- the first differing reference word or character is highlighted;
- the expected and entered character are stated below the model text;
- the remaining untyped passage remains visually distinct;
- extra characters after the passage are explicitly reported;
- **Finished Typing** is enabled only after an exact normalized match.

An optional **Pause & Review Difference** control stops telemetry while the participant inspects the highlighted mismatch. **Resume Corrections** starts a new timing segment. The review interval is therefore not treated as a keystroke flight, digraph, trigraph, or typing-duration interval.

The feature extractor also separates the two concepts statistically:

- flights of at least 500 ms continue to inform **Pause Pattern**;
- only sub-500-ms flight variation informs **Consistency Score**;
- hold-time variation remains part of Consistency Score.

This prevents a single validation or reading pause from being counted both as pause behavior and as motor-rhythm inconsistency. Metric vectors record `feature_version=4.2` for reproducibility.

## UI controls

- Navigation between screens uses **Continue**.
- The final results screen uses **Submit**.
- Typing activities retain **Start Typing** and **Finished Typing**.
- Fixed text adds the contextual **Pause & Review Difference** / **Resume Corrections** control only when needed.
- There is no participant navigation menu.

## Cache correction

The release uses versioned assets:

- `participant-v2.css?v=4.2.0`
- `participant-v2.js?v=4.2.0`

The `/` route sends a `no-store` cache header so an earlier participant interface is not silently reused after restart.
