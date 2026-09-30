# RadSpeed model comparison — 30 September 2026

## Decision

Keep GPT-6 Sol with low reasoning. Sol 6.1 did not meet the speed requirement.
Production model settings remain unchanged. No new sonographer worksheet comparison was run.
The worksheet phase was conditional on faster report creation. That condition was not met.

## Speed

Both models used low reasoning and Standard processing. Values below are medians.

| Task | Tests per model | Sol 6 | Sol 6.1 | Sol 6.1 change |
|---|---:|---:|---:|---:|
| Complete full report | 18 | 4.41 s | 5.35 s | 21.2% slower |
| Complete impression | 9 | 1.18 s | 1.52 s | 28.9% slower |
| First text of full report | 18 | 1.97 s | 1.37 s | 30.4% faster |

Sol 6.1 began full reports sooner. It took longer to finish them.
The knee report was 3.2% faster by case median. This small difference did not justify a switch.

## Accuracy review

Sol 6.1 retained the tested main abnormalities, measurements and side labels.
The existing Sol 6 model omitted the right knee side label in one full report and one impression.
Both models expanded the existing normal template text. These statements were not independently verified against images.
Sol 6.1 expanded the heart-strain section in one PE report with normal RV:LV, septal and reflux observations.
The template requests those observations. The synthetic dictation did not provide each observation separately.
This is a source-fidelity limitation. It is not evidence of clinical accuracy.

The automatic checker flagged wording differences such as “no evidence of” and “without”.
Manual review confirmed the same negative meaning in those flagged Sol 6.1 outputs.
Raw checker scores are therefore not clinical accuracy percentages. The original flags remain in the results.

## Method and limits

- Six synthetic dictations: negative CT head, pulmonary embolus, meniscal tear, ureteric calculus, thalamic infarct and pneumothorax.
- Three full-report runs per case and model. Three impression runs for PE, meniscus and infarct per model.
- 54 timed report requests, plus two short availability checks.
- Model order alternated within pairs. Calls ran serially on the production server through its existing provider.
- Both models used identical prompts, templates, low reasoning and Standard processing. No Fast processing was tested.
- Full reports used the selected-template streaming route. Impressions used the existing streaming route with guideline matching enabled.
- Times include the provider call and local report processing. They exclude audio transcription, browser display and clipboard transfer.
- Only synthetic data were used. No clinical accuracy rate or production-wide speed guarantee was established.
- The test process changed its own model selection only. Saved settings and live application workers were not changed.
- The comparison finished successfully. The temporary server access rule was closed successfully.

## Results by case

| Task and case | Sol 6 median | Sol 6.1 median | Sol 6.1 change |
|---|---:|---:|---:|
| report: ct head negative | 4.73 s | 5.36 s | 13.5% slower |
| report: ct kub left ureteric calculus | 4.34 s | 5.43 s | 25.1% slower |
| report: ctpa right lower lobe embolus | 4.79 s | 5.63 s | 17.5% slower |
| report: cxr right pneumothorax | 3.15 s | 4.01 s | 27.4% slower |
| report: mri brain left infarct | 4.68 s | 6.03 s | 28.9% slower |
| report: mri knee medial meniscus | 4.09 s | 3.96 s | 3.2% faster |
| impression: ctpa right lower lobe embolus | 1.17 s | 1.30 s | 10.9% slower |
| impression: mri brain left infarct | 1.18 s | 1.76 s | 48.8% slower |
| impression: mri knee medial meniscus | 1.17 s | 1.54 s | 32.4% slower |

## Evidence

[Successful test run](https://github.com/markbekhit/RadSpeed/actions/runs/36706224164)

[All generated synthetic drafts](/Users/markbekhit/Developer/products/radspeed/reports/model-comparison-2026-09-30/generated-drafts.md)

[Original measurements and automatic checks](/Users/markbekhit/Developer/products/radspeed/reports/model-comparison-2026-09-30/results.json)
