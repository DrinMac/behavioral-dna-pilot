# Deployment Checklist

## Research governance

- [ ] Ethics/institutional approval completed
- [ ] Consent wording approved
- [ ] Participant inclusion/exclusion criteria documented
- [ ] Data-retention and deletion schedule documented
- [ ] Withdrawal and researcher contact information added
- [ ] Baseline and final-test session allocation prespecified
- [ ] Impostor protocol prespecified
- [ ] Threshold-development data separated from final test data

## Platform configuration

- [ ] `APP_ENV=production`
- [ ] Random `SECRET_KEY` configured
- [ ] Strong `RESEARCHER_PASSWORD` configured
- [ ] Durable PostgreSQL `DATABASE_URL` configured
- [ ] `TARGET_SESSIONS` confirmed
- [ ] `CONSENT_VERSION` confirmed
- [ ] `STUDY_CONTACT` updated
- [ ] `STORE_KEY_VALUES=false` unless explicitly approved
- [ ] HTTPS confirmed

## Functional pilot

- [ ] First-time registration works
- [ ] `DNA-XXXXX` and recovery PIN are displayed
- [ ] Same-browser automatic recognition works
- [ ] Manual restoration works on a second browser
- [ ] Browser/OS/device values are correct
- [ ] Keyboard selection is required
- [ ] Fixed and free telemetry capture works
- [ ] Pasting is blocked and logged
- [ ] Initial/Fixed/Free/Combined metrics display
- [ ] Final submission increments participant progress
- [ ] Ten-session completion behavior works
- [ ] Researcher login works
- [ ] Baseline session selection works
- [ ] Baseline sessions are blocked from final evaluation
- [ ] Evaluation and fusion configuration work
- [ ] ZIP export downloads and opens

## Operational monitoring

- [ ] Health endpoint checked daily
- [ ] Database persistence tested after restart
- [ ] Participant completion counts reviewed daily
- [ ] Analyzed-but-unsubmitted sessions reviewed
- [ ] Quality warnings reviewed
- [ ] Export backup created at least daily during collection
