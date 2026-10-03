# Sol 6.1 repeat benchmark — 3 October 2026


## Decision


Keep Sol 6 and the standard two-step worksheet method. Sol 6.1 completion speed did not improve materially.


## Completion time


All values are medians. Sol 6 was not repeated. Its results are from 30 September.

| Task | Runs today | Sol 6 saved | Sol 6.1 saved | Sol 6.1 today | Change from previous Sol 6.1 |
|---|---:|---:|---:|---:|---:|
| Full report | 18 | 4.41 s | 5.35 s | 5.26 s | 1.6% faster |
| Impression | 9 | 1.18 s | 1.52 s | 1.70 s | 11.8% slower |
| Worksheet, one step | 6 | 6.51 s | 8.27 s | 8.25 s | 0.3% faster |
| Worksheet, two steps | 6 | 7.62 s | 9.54 s | 9.53 s | 0.2% faster |


Full reports were 1.6% faster than the previous Sol 6.1 test. Worksheet completion times were essentially unchanged.

Compared with saved Sol 6, current Sol 6.1 was about 19% slower for reports and 44% slower for impressions. It was about 27% slower for one-step worksheets and 25% slower for two-step worksheets.


## First text and worksheet stages


Full reports began at 1.18 seconds, versus 1.37 seconds previously. This is 13.4% sooner. Earlier first text did not produce a material reduction in completion time.

Extraction median: 4.90 seconds.

Formatting median: 4.61 seconds.


## Source-fidelity review


- All 18 full reports retained the reviewed main abnormalities, side labels, dictated measurements, and relevant negatives. Equivalent units and negative wording caused some automatic flags.

- One of three knee impressions omitted the dictated right-side label. The other two included it.

- All 12 worksheet drafts and source notes retained the reviewed measurements, side bindings, checked findings, and view limitations.

- All six obstetric drafts retained BPD and the entered repeat-imaging recommendation. No BP substitution was found.

- Unticked renal history options were not copied into these source notes or reports.

- No unsupported anatomy or growth conclusion was found in these worksheet outputs.

- Full reports still expand unmentioned normal template text. This remains a shared source-fidelity limitation.

- Impression-only reports intentionally summarise the input. For example, they need not repeat every negative or pulmonary-artery measurement. These small synthetic tests do not establish clinical accuracy.


## Method and limits


The same six synthetic dictations and two synthetic worksheet images were used. Each case and route ran three times. There were 39 completed drafts, 45 task calls, and one availability call. No failures occurred.

The benchmark ran serially through the same Sydney production server and direct OpenAI endpoint. Both historical and current tests used low reasoning and the default Standard service tier. Every returned service tier was verified.

The benchmark used the same report-template streaming route, guideline-enabled impression route, and one-step and two-step worksheet functions. Prompt-building code and the tested fixtures/templates were unchanged. Recent application edits add local numeral formatting and CT CAP selection; these do not change the tested selected-template request prompts.

Times exclude audio transcription, browser display, user review and clipboard transfer. These are historical comparisons rather than a new paired comparison. Provider load, cache behaviour and response length can vary.

The tests do not establish whether launch demand caused the prior timing. They show no substantial completion-speed gain in these workflows today.

Saved production settings and live workers were unchanged. The workflow closed its temporary server access successfully.


## Evidence


[Successful server benchmark](https://github.com/markbekhit/RadSpeed/actions/runs/37114145150)

[Generated synthetic drafts](/Users/markbekhit/Developer/products/radspeed/reports/sol61-retest-2026-10-03/generated-drafts.md)

[Raw measurements](/Users/markbekhit/Developer/products/radspeed/reports/sol61-retest-2026-10-03/results.json)

[Calculated comparison](/Users/markbekhit/Developer/products/radspeed/reports/sol61-retest-2026-10-03/comparison.json)
