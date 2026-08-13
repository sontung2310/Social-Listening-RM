# gpt-5-nano improve loop (200 rows)

| Task | R0 (v1.1) | R1 (v1.2) | R2 (classify v1.2 + extract v1.3) |
| --- | --- | --- | --- |
| Overall | 135 / 200 (67.5%) | 138 / 200 (69.0%) | 160 / 200 (80.0%) |
| Sentiment | 177 / 200 (88.5%) | 171 / 200 (85.5%) | 176 / 200 (88.0%) |
| Topic | 131 / 200 (65.5%) | 142 / 200 (71.0%) | 154 / 200 (77.0%) |
| Keywords | 154 / 200 (77.0%) | 147 / 200 (73.5%) | 158 / 200 (79.0%) |
| Summary | 57 / 76 (75.0%) | 53 / 80 (66.2%) | 86 / 92 (93.5%) |

| Metric | R0 | R1 | R2 |
| --- | --- | --- | --- |
| Mean latency | 2763.8 ms | 2826.6 ms | 2274.5 ms |
| Rows with summary | 59 | 59 | 90 |
| keyword_noise | 43 | 51 | 40 |
| summary_hallucination | 2 | 6 | 2 |
| summary_missing / empty_summary | 5/11 | 10/8 | 2/0 |

## Causes fixed in R2
- Keywords: v1.2 anti-fragment rules pushed nano into awkward spans; v1.3 restores clear word-cloud noun phrases + hashtag few-shots + fragment drop in validate.
- Summary: `NLP_SUMMARY_MIN_CHARS` 400→220 so mid-length posts get summaries; summary rules now prefer thesis-level faithfulness (fewer hallucinations).
