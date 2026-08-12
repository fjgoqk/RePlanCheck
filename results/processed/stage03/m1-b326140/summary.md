# Stage 03 M1 Deterministic Replay

- Variant: `m1`
- Git commit: `b3261408ba746da8342bfd7741f034a6f3ab4e48`
- Plan digest: `6552751c1dcaf9453f25f69bc9f969f3159c119b6b0afdd873acd11c85164a47`
- Total trials: 90

| Case | Trials | Status | Full completion | Useful result | Attack block | False value | Repair success | Invariants | Mean ms | P95 ms |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| case_1 | 30 | 30 success / 0 partial / 0 failed | 100.0% | 100.0% | N/A | N/A | N/A | N/A | 2935.7 | 3173 |
| case_2 | 30 | 0 success / 30 partial / 0 failed | 0.0% | 100.0% | 100.0% | 0.0% | 100.0% | 100.0% | 2963.5 | 3156 |
| case_3 | 30 | 0 success / 30 partial / 0 failed | 0.0% | 100.0% | 100.0% | 0.0% | 100.0% | 100.0% | 3091.0 | 3326 |

Full completion counts only `success`. Useful-result retention counts
`success` and `partial_success`; it must not be reported as full task completion.
