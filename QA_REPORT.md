# Quality Assurance Report

## Package reviewed

`Behavioral_DNA_Study_Deployable` — Release 4.2

## Validation date

30 July 2026

## Automated checks completed

| Check | Result |
|---|---|
| Python application compilation (`python -m compileall -q app`) | Passed |
| Participant JavaScript syntax (`node --check`) | Passed |
| Researcher JavaScript syntax (`node --check`) | Passed |
| Automated tests (`PYTHONPATH=. pytest -q`) | Passed: 3 tests |
| Participant page HTTP response | Passed: HTTP 200 |
| Researcher page HTTP response | Passed: HTTP 200 |
| Health endpoint | Passed: `status=ok` |

## Participant fixed-text checks

- Versioned Release 4.2 participant assets are served.
- The model passage provides live correct, pending, mismatch, and extra-text states.
- The first differing character and affected reference word are identified.
- Finished Typing remains unavailable until the normalized passage matches exactly.
- Pause & Review stops the active recorder.
- Resume Corrections creates a distinct fixed-text timing segment.
- A synthetic long review interval between correction phases does not become a flight, digraph, trigraph, pause, or consistency penalty.
- Pause Pattern remains responsible for genuine within-segment pauses of at least 500 ms.
- Consistency Score uses hold variation and sub-500-ms flight variation.

## End-to-end scenario covered

The automated test validates the following operational chain:

1. Register two pseudonymous participants.
2. Create remembered participant sessions.
3. Capture and calculate Initial, Fixed, Free, and Combined metric vectors.
4. Complete repeated longitudinal typing sessions.
5. Build an enrollment baseline from explicitly selected session IDs.
6. Reject accidental reuse of baseline sessions as holdout evaluation sessions.
7. Evaluate a genuine holdout session and a cross-participant impostor session.
8. Run Z-score, Behavioral Envelope, Mahalanobis, and Drift calculations.
9. Apply configurable weighted fusion and decision thresholds.
10. Produce confusion-matrix and authentication evaluation results.
11. Generate the complete research data ZIP export.

## Design checks

- The participant interface uses a continuous guided flow with no navigation menu.
- The final participant action is **Submit**; intermediate transitions use **Continue**.
- Same-browser participant recognition uses a random device token.
- Manual recovery uses the participant's `DNA-XXXXX` code and recovery PIN.
- Printable key values are not stored by default (`STORE_KEY_VALUES=false`).
- The Combined vector consistently represents Fixed + Free telemetry only.
- Initial registration telemetry remains separately available for Session 1.
- Browser, operating system, device type, and keyboard type are stored per session.
- Every baseline stores the exact selected session database IDs and activity scope.
- Every evaluation run stores the baseline, selected test session IDs, engine configuration, fusion configuration, thresholds, and results.

## Deployment status

The source package includes a Dockerfile, Docker Compose configuration, Render Blueprint, and PostgreSQL support. The application was validated directly in the supplied execution environment. A Docker daemon was not available in this environment, so the container image itself could not be built here. The included commands and deployment checklist should be followed in the target hosting account, with a final prelaunch test using two test participants before opening recruitment.

## Release recommendation

The package is suitable for a controlled one-week pilot after the researcher completes the ethical, privacy, consent, retention, study-contact, and hosting configuration items in `DEPLOYMENT_CHECKLIST.md`. It should not be treated as a production identity-authentication service.
