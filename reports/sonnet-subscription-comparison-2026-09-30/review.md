# Sonnet 5.5 subscription comparison — 30 September 2026

## Result

Sonnet 5.5 completed all 39 drafts using the existing Claude Max subscription session.
No paid API key was used. Existing Sol 6 and Sol 6.1 results were reused without new baseline calls.
Sol 6 remained faster for the complete measured process. Production models and worksheet routes remain unchanged.

## Speed

All times are medians. Sonnet total includes launching Claude Code. The model-call column uses Claude Code’s reported API duration.

| Task | Drafts per model | Sol 6 saved total | Sol 6.1 saved total | Sonnet model-call time | Sonnet total |
|---|---:|---:|---:|---:|---:|
| Full report | 18 | 4.41 s | 5.35 s | 3.52 s | 5.16 s |
| Impression | 9 | 1.18 s | 1.52 s | 1.63 s | 3.10 s |
| Worksheet: one step | 6 | 6.51 s | 8.27 s | 6.68 s | 7.95 s |
| Worksheet: two steps | 6 | 7.62 s | 9.54 s | 6.68 s | 9.66 s |

The reported Sonnet model-call time looks promising for full reports and two-step worksheets.
It is not a direct API speed comparison: the route, location, automatic caching and measurement definitions differ.
The complete subscription route was slower than the saved Sol 6 route in each aggregate task.
Model-call times cannot establish what Sonnet would achieve through RadSpeed’s production API.

## Worksheet results by example

| Worksheet | Route | Sonnet model-call median | Sonnet total median |
|---|---|---:|---:|
| Renal | One step | 9.99 s | 11.26 s |
| Renal | Two steps | 6.58 s | 9.58 s |
| Obstetric | One step | 6.59 s | 7.90 s |
| Obstetric | Two steps | 6.79 s | 9.74 s |

Sonnet two-step was faster on the renal example. One-step was faster on the obstetric example.
There was no consistent one-step advantage across worksheet types.

## Source-fidelity review

- All reviewed drafts retained the tested main abnormalities, measurement magnitudes and side labels.
- All 12 worksheet reports retained BPD correctly, the entered measurements and centiles, the left-sided abnormalities, incomplete RVOT/upper-lip views, and the entered repeat-imaging recommendation.
- All three one-step renal source-note outputs also listed unticked history options. The report did not convert those options into clinical negatives.
- One two-step obstetric impression added that biometry was appropriate for gestational age. That assessment was not entered on the worksheet.
- One two-step renal impression added a low-residual qualifier not entered on the worksheet.
- All three PE impressions added a mild pulmonary artery enlargement interpretation. Two added possible pulmonary hypertension and echocardiography advice. The impression route has guideline matching enabled; these additions were not in the dictation and carry no displayed source citation.
- Two brain impressions added an otherwise-unremarkable statement beyond the dictated observations.
- Some full reports converted equivalent units, such as 29 mm to 2.9 cm. No worksheet measurement conversion was found.
- Full reports expanded normal template defaults, as in the existing Sol tests. Those statements were not verified against images.

Sonnet did not show a clear source-fidelity advantage sufficient to justify a switch.
The reports still need radiologist review. This synthetic test does not estimate clinical accuracy.

## Subscription adapter and limits

- Auth was verified as claude.ai, firstParty, and Max before the run. Every accepted response confirmed claude-sonnet-5-5.
- Three repeats used the same six synthetic dictations, the same two worksheet PNGs, the same report templates, and the existing application report functions.
- 18 full reports, nine impressions, six one-step worksheets and six two-step worksheets completed: 39 drafts and 45 successful underlying model calls.
- The adapter used Claude Code with low effort, safe mode, no tools, no slash commands and no stored benchmark sessions. Prompt input used temporary files, deleted after each call.
- Claude Code’s low effort setting is not an identical reasoning budget to OpenAI low. Its reported thinking token counts are retained.
- Claude Code adds its own request context and automatic prompt caching. It does not expose the OpenAI temperature, output-budget or response-format controls used by the direct API route.
- Initial one-step attempts returned Markdown-fenced JSON, which the application rejected. The adapter removes an outer JSON fence only; it never repairs JSON or changes source notes or reports. The two initial parser failures remain in the raw results and are excluded from successful timing medians.
- The process resumed after the adapter fix. Previously completed Sonnet reports were reused. No Sol model was called again.
- This CLI adapter is evaluation-only and is not a production integration. No patient data, new provider credential or subscription credential extraction was involved.
- Times exclude audio transcription, browser upload, clinical review and clipboard transfer. Historical baseline times came from the Sydney server; this subscription test ran on the Mac.
- No Fast-tier or high-effort Sonnet test was run. No production settings or application workers were changed.

## Evidence

[All generated drafts](/Users/markbekhit/Developer/products/radspeed/reports/sonnet-subscription-comparison-2026-09-30/generated-drafts.md)

[Timing and usage records](/Users/markbekhit/Developer/products/radspeed/reports/sonnet-subscription-comparison-2026-09-30/results.json)

[Individual quality review](/Users/markbekhit/Developer/products/radspeed/reports/sonnet-subscription-comparison-2026-09-30/quality-review.json)

[Saved Sol report comparison](/Users/markbekhit/Developer/products/radspeed/reports/model-comparison-2026-09-30/review.md)

[Saved Sol worksheet comparison](/Users/markbekhit/Developer/products/radspeed/reports/worksheet-model-comparison-2026-09-30/review.md)

[Sonnet 5.5 model documentation](https://platform.claude.com/docs/en/models/sonnet-5-5/overview)
