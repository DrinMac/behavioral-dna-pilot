# Prototype Review and Rebuild Summary

## Existing strengths found in the attached prototype

- Actual browser telemetry replaced simulated timing.
- The eight requested aggregate metrics were already present.
- Baseline generation included mean, standard deviation, lower/upper envelopes, correlation, inverse correlation, and readiness information.
- Z-score, envelope, Mahalanobis, and drift calculations were implemented.
- Fusion and multi-level decisions were implemented.
- Evaluation included confusion-matrix measures, FAR, FRR, AUC, and EER.
- Raw events, feature vectors, baselines, engine results, and decisions were persisted.

## Gaps addressed by this rebuild

- The original interface primarily exposed researcher/test controls rather than a participant-friendly longitudinal process.
- Users were ordinary named profiles rather than pseudonymous research participants.
- Session return recognition and recovery were not designed for a one-week online study.
- Registration, consent, demographics, browser/device context, and keyboard information were not integrated into one participant journey.
- Initial, Fixed, Free, and Combined vectors were not represented as consistent activity scopes in each study session.
- Baseline creation was user-wide rather than explicitly selected by study-session IDs in the main workflow.
- Baseline/test overlap was not prevented by the evaluation workflow.
- The database used SQLite only and was not directly configured for a durable managed PostgreSQL deployment.
- Printable key values were stored by default without a privacy-oriented deployment switch.
- The researcher console did not provide the requested participant progress, baseline selection, four-engine configuration, and export flow in one focused interface.

## Calculation refinements

- Flight time is computed from paired strokes as current keydown minus previous keyup, preserving legitimate negative overlaps.
- Hold time uses matched keydown/keyup events by segment and code.
- Digraph and trigraph timing chains reset between fields.
- Typing duration is summed within active fields rather than including page-transition time.
- Pause calculations use nonnegative flight intervals.
- Combined is Fixed + Free for every session, preserving longitudinal comparability.
- Initial registration telemetry is reported independently.

## Deployment footprint refinement

The rebuilt evaluation module calculates ROC AUC and EER internally, and the Mahalanobis engine uses the fixed chi-square critical values for eight metrics. This removes SciPy and scikit-learn from the runtime while preserving the configured four-engine behavior.
