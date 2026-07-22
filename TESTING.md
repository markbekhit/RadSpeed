# Testing RadSpeed

RadSpeed uses layered tests so failures are caught at the cheapest reliable
level while the clinical and browser-critical paths still receive end-to-end
coverage. The test data is synthetic and must never contain patient information.

## Test layers

- **Python unit/integration:** `python -m unittest discover -v`
  covers transcription, formatting/templates, clinical safety rules, silent
  failures, and file-drop integrations.
- **Browser E2E:** `pytest e2e --browser chromium`
  starts an isolated local server with `VOXRAD_MOCK_MODE=1`, uses HTTP Basic
  Auth, and exercises public Impressions plus authenticated transcription and
  streamed formatting. It also covers keyboard-first reporting, automatic
  laterality-aware QA, atomic worklist case switching, compact patient focus,
  deterministic follow-up prompting, and manual score insertion. External model
  calls are routed to local mock endpoints.
- **Clinical quality:** `python -m evals.clinical_quality`
  validates the reviewed synthetic references. Use
  `python -m evals.clinical_quality --live --minimum-pass-rate 0.80` only in an
  environment with the configured text-model key. Live evals use six synthetic
  cases and never patient data.
- **Live production QA:** browser smoke testing confirms the deployed UI and
  synthetic Impressions flow after material web changes.

## Setup

```bash
python -m pip install -r requirements-test.txt
python -m playwright install chromium
```

For a CI-equivalent local run:

```bash
python -m unittest discover -v
python -m evals.clinical_quality
pytest e2e --browser chromium --tracing=retain-on-failure
```

## Conventions

- Add a regression test for every bug fix.
- Mock external providers in automated tests; never spend API credits in the
  standard CI gate.
- Assertions must verify user-visible behavior or clinical facts, not merely
  that a value exists.
- Clinical cases protect dictated findings, negation, laterality,
  measurements, and report section order without requiring one exact wording.
- Keep live model evaluation separate from deployment gating because model
  output is probabilistic; its scheduled workflow is an early-warning signal.
