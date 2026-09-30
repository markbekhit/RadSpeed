# Worksheet model comparison — 30 September 2026

## Decision

Keep the current production model and the standard two-step route. Sol 6.1 was slower in both routes.
Sol 6.1 preserved the repeat-imaging recommendation more reliably in the two-step obstetric example.
Sol 6 one-step was fastest overall and retained the reviewed source facts in these examples.
These two examples do not justify making one-step processing the clinical default.

## Complete draft times

All times are medians. Each cell contains three repeats of the same synthetic image.

| Worksheet | Route | Sol 6 | Sol 6.1 | Sol 6.1 change |
|---|---|---:|---:|---:|
| Renal | One step | 6.64 s | 8.18 s | 23.1% slower |
| Renal | Two steps | 6.77 s | 9.39 s | 38.6% slower |
| Obstetric | One step | 6.24 s | 8.38 s | 34.3% slower |
| Obstetric | Two steps | 8.40 s | 9.96 s | 18.6% slower |
| Both | One step | 6.51 s | 8.27 s | 27.1% slower |
| Both | Two steps | 7.62 s | 9.54 s | 25.3% slower |

One step reads the image and returns source notes plus the report in one call.
Two steps extract source notes, then format a report in a second call.
Across both examples, Sol 6 one-step took 14.5% less time than Sol 6 two-step.
For renal worksheets, Sol 6 two-step was almost as fast as one-step: 6.77 versus 6.64 seconds.

## Source fidelity

- All 24 drafts retained the reviewed measurements, side labels, main abnormalities, and incomplete-view limitations.
- All routes retained BPD correctly, either as BPD or the full term biparietal diameter. No BP substitution was found.
- No right/left swap or unsupported normal statement was found in the reviewed outputs.
- Sol 6 two-step omitted the entered repeat-imaging recommendation in two of three obstetric runs. The omission began in image extraction.
- One of those Sol 6 two-step reports also added “Fetal biometry is appropriate for the stated gestational age.” The worksheet did not document that conclusion.
- Sol 6.1 retained the recommendation in every obstetric source note and report. In one two-step draft, it appeared in Findings only.
- Both one-step routes retained the reviewed source facts in all six drafts per model. Impression inclusion of incidental simple cysts and mild prostatomegaly varied; the findings retained them.

The two-step route exposes the extraction for review, but it can still omit source observations.
These observations are a small synthetic comparison, not a clinical accuracy rate.

## Processing and token use

| Route | Model | Mean input tokens per draft | Mean output tokens per draft | Mean reported reasoning tokens |
|---|---|---:|---:|---:|
| One step | gpt-6-sol | 2494 | 536 | 45 |
| One step | gpt-6.1-sol | 2494 | 505 | 0 |
| Two steps | gpt-6-sol | 5279 | 542 | 49 |
| Two steps | gpt-6.1-sol | 5305 | 536 | 0 |

Output totals include reported reasoning tokens. For two steps, input and output totals sum both calls.
Sol 6.1 used slightly fewer total output tokens. It still took longer to finish.
The API reported zero reasoning tokens for Sol 6.1; this does not prove that the model performed no internal reasoning.
Two-step median stage times were 3.80 seconds extraction and 3.69 seconds formatting for Sol 6.
Sol 6.1 took 4.80 seconds extraction and 4.88 seconds formatting. Neither stage offered a speed advantage.

## Method and limits

- Two synthetic screenshots: renal tract and second-trimester obstetric. No patient data were used.
- Two models, two routes, three repeats: 24 complete drafts and 36 worksheet API calls. Two additional availability calls were excluded from worksheet timings.
- Calls ran serially. Model order alternated by image and repeat. The report template, images, low reasoning setting, and Standard service tier were fixed.
- Returned API service tiers were verified as default for every worksheet call. Token usage was recorded.
- Timing includes image reading, report generation and local processing. It excludes image upload from the browser, user review and clipboard transfer.
- A cancelled preliminary report comparison is excluded. It might have briefly overlapped the first worksheet repeat. The later repeats independently showed Sol 6.1 slower in every paired comparison.
- No high-reasoning, Fast-tier, mixed-model, degraded-image or real-handwriting comparison was performed.
- Saved model settings, live workers and worksheet defaults were not changed. Both runs closed their temporary server access successfully. The production health check passed.

## Evidence

[Successful worksheet test](https://github.com/markbekhit/RadSpeed/actions/runs/36707937886)

[All generated drafts](/Users/markbekhit/Developer/products/radspeed/reports/worksheet-model-comparison-2026-09-30/generated-drafts.md)

[Timings and token usage](/Users/markbekhit/Developer/products/radspeed/reports/worksheet-model-comparison-2026-09-30/results.json)

[Individual source-fidelity reviews](/Users/markbekhit/Developer/products/radspeed/reports/worksheet-model-comparison-2026-09-30/quality-review.json)
