# Sonnet 5.5 speed reassessment (Claude Code, Claude Max subscription)

Date: 2026-10-01. Synthetic inputs only. Claude Code prepared the review; the parent verified timings and source-note checks. Evidence: [results.json](/Users/markbekhit/Developer/products/radspeed/reports/sonnet-reassessment-2026-10-01/results.json), [comparison.json](/Users/markbekhit/Developer/products/radspeed/reports/sonnet-reassessment-2026-10-01/comparison.json), [automated-review-flags.json](/Users/markbekhit/Developer/products/radspeed/reports/sonnet-reassessment-2026-10-01/automated-review-flags.json), [generated-drafts.md](/Users/markbekhit/Developer/products/radspeed/reports/sonnet-reassessment-2026-10-01/generated-drafts.md). Source: `evals/sonnet_reassessment.py`, `evals/sonnet_reassessment_compare.py`.

## Question and method

Could Sonnet be faster than the earlier saved comparison once route delay is removed? Claude Code ran the benchmark itself, delegated by the user, using only their Claude Max login (`claude.ai`, firstParty, no API key). Model `claude-sonnet-5-5`, effort `low`, 3 repeats. No production settings were changed and no Sol call was repeated. Sol figures are historical, from [reports/model-comparison-2026-09-30](/Users/markbekhit/Developer/products/radspeed/reports/model-comparison-2026-09-30/review.md) and [reports/worksheet-model-comparison-2026-09-30](/Users/markbekhit/Developer/products/radspeed/reports/worksheet-model-comparison-2026-09-30/review.md).

117 completed synthetic drafts, 0 failed attempts, across three conditions:

- `cli_default`: standard CLI.
- `cli_lean`: `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` set.
- `cli_lean_no_thinking`: supplementary. `MAX_THINKING_TOKENS=0` was requested (see the correction below).

Tasks per condition: 18 full reports, 9 impressions, 6 one-step worksheets, 6 two-step worksheets. Each call is a fresh stateless CLI request using the matched RadSpeed source prompts, templates and fixtures.

## Headline numbers (median total seconds to process exit, low effort)

| Task | Sol 6 (saved) | Sonnet default | Sonnet lean |
|---|---|---|---|
| Full report | 4.41 | 4.762 | **3.699** |
| Impression | 1.18 | 3.192 | 1.777 |
| Worksheet one-step | 6.51 | 7.193 | 7.400 |
| Worksheet two-step | 7.62 | 10.551 | **7.332** |

Sol 6.1 saved medians were 5.35, 1.52, 8.27 and 9.54.

Lean Sonnet beat saved Sol 6 on full reports and two-step worksheets. It was slower on impressions and one-step worksheets. The two-step gain is small and each cell is n=6, so I would not treat it as a stable ranking.

## Observed route delay

The default CLI spent about 0.65 s in start-up and 0.8 to 1.5 s in teardown. That is about 1.5 s of start-up plus exit overhead per call, A trivial probe took 2.75 s in total, including its model call. The lean condition cut this to about 0.2 s (start-up about 0.19 s, teardown about 0.01 s). Provider timings did not consistently improve: full reports took 3.14 s default versus 3.48 s lean.

The gain is therefore overhead removal, not faster generation. Disabling nonessential traffic coincided with the change, but the data do not prove that any specific background service was the sole cause.

The floor probe (n=5 per condition, `cli_lean_no_thinking` not probed) gave median exit of 2.75 s default and 1.47 s lean, with median provider time of about 1.2 s in both.

## Correction: the "no thinking" condition is not valid

`MAX_THINKING_TOKENS=0` did not consistently disable thinking. Of the 45 calls in `cli_lean_no_thinking`, 3 reported thinking tokens (1,417 in total). For comparison, `cli_default` had 3 calls with 1,549 tokens and `cli_lean` had 7 calls with 4,222 tokens. The label `cli_lean_no_thinking` states intent only. It is not a verified zero-thinking condition and not a valid controlled comparison. Its speed differences are exploratory. They were: report 3.51 s, impression 1.93 s, one-step 6.74 s, two-step 6.97 s.

## Limitations

- Subscription-only testing cannot establish direct production API speed. Provider-reported time (CLI/first-party) and historical OpenAI request wall-time are different clocks. Caching (cache-read share 0.79 to 0.88), server location, date and internal CLI context also differ from the Sol runs.
- Sol is a historical, non-concurrent baseline. It was not re-run, so drift cannot be excluded.
- The persistent-conversation probe carried earlier context (cache creation grew from 879 to 963 tokens). It cannot demonstrate a valid faster stateless equivalent.
- Small samples: 3 repeats on 2 to 6 cases per task. Medians only, with no confidence intervals.
- Four of six one-step worksheet drafts in `cli_default`, and all six in `cli_lean`, came back wrapped in JSON fences that the harness removed. This is a parse-robustness cost that raw speed does not show.
- Automated phrase gates: 17 of 18 reports passed in `cli_default` and in `cli_lean`, and 18 of 18 in `cli_lean_no_thinking`. One full knee report omitted the dictated right-side label. The PE flag was equivalent wording: “no evidence of right heart strain”. Scores are phrase matches, not clinical accuracy.
- Dictated-report template-normal expansion is a shared limitation. Models fill unmentioned template sections with normal text, for example "Sulci unremarkable" on the head CT. This needs a clinician's judgement for any model, and I did not score it.

## Independent source-fidelity review

I read the renal and obstetric worksheet images and compared all 36 worksheet drafts and their extracted source notes. The checks covered exact measurements, side binding, BPD, not-seen anatomy, the entered repeat recommendation, unchecked choices, and unsupported normal or growth assertions. I also read [automated-review-flags.json](/Users/markbekhit/Developer/products/radspeed/reports/sonnet-reassessment-2026-10-01/automated-review-flags.json).

**Worksheets, no missing facts:**
- All values were present in every draft. Renal: 10.8/10.2 cm, 14/12 mm, 9 mm AP pelvis, 6 mm lower-pole calculus, 2.1 × 1.7 × 1.5 cm right cyst, 318/24/3/36 mL and mm values. Obstetric: GA, FHR, cervix, placenta, BPD 52 mm, HC, AC, FL, EFW and centiles.
- Left/right binding was correct throughout, including right-only cyst, left-only calculus and left pelvicaliectasis, and left fetal pyelectasis.
- RVOT and upper lip were kept as "not well seen". "Repeat imaging recommended" was carried through, because the worksheet entered it.
- Unticked options were not asserted as clinical negatives in reports. However, all nine one-step renal source-note outputs listed unticked history choices, contrary to the extraction rules.
- The automated worksheet flags for "missing 2.1" (2 drafts) are wording, not omissions. "2.1 x 1.7 x 1.5" versus "×" is an equivalence.

**One real unsupported assertion:** two-step obstetric `cli_lean` repeat 1 impression item 3 says "the remaining documented fetal anatomy is normal, with biometry and estimated fetal weight at appropriate centiles". The worksheet records centiles only. It makes no growth-adequacy statement and no global normal statement, so this is unsupported. The same phrase appeared nowhere else in the 36 worksheet drafts.

**Extra impression content (not wording equivalence):** the automated flag for `ctpa_right_lower_lobe_embolus` is a true positive. 6 of the 9 impression outputs (2 per condition) added an unrequested main pulmonary artery line. The "2.9 cm" is a units conversion of the dictated 29 mm and is fine. The added "may reflect pulmonary hypertension", "echocardiography suggested" and "upper limit of normal calibre" wording is interpretation that the dictation does not support. The other impression cases were clean, and the flag counts were identical across conditions, so this is not a speed-condition artefact. Another CTPA impression in `cli_lean` repeat 1 shows the model adding numbered items, which the flagger picked up as noise.

The traffic setting is documented in [Claude Code’s environment-variable reference](https://code.claude.com/docs/en/env-vars). It applied only to benchmark child processes.

## Recommendation

1. Do not switch models on speed evidence from this run. Lean Sonnet wins two tasks, loses two, and all margins are within what n=6 to 18 and a different timing clock can hide.
2. The clear finding is that CLI overhead, about 1.3 s per call, is removable with nonessential traffic disabled. That is a property of this harness, not of the production API, and it needs an API-path measurement before it informs a model decision.
3. Treat `cli_lean_no_thinking` as exploratory and do not cite it as a no-thinking result.
4. If Sonnet is considered later, run a same-day interleaved comparison through the production path, and add a prompt constraint against unrequested interpretation in impressions (the CTPA pulmonary artery addition) before any clinical use. Clinician review of unsupported normal/growth statements remains necessary for every model.
