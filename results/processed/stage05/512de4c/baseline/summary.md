# Stage 03 BASELINE Deterministic Replay

- Variant: `baseline`
- Git commit: `512de4c690b4d61ab84b194f58b689cca98f1a84`
- Plan digest: `6552751c1dcaf9453f25f69bc9f969f3159c119b6b0afdd873acd11c85164a47`
- Total trials: 90

| Case | Trials | Status | Full completion | Useful result | Attack block | False value | Repair success | Invariants | Mean ms | P95 ms |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| case_1 | 30 | 30 success / 0 partial / 0 failed | 100.0% | 100.0% | N/A | N/A | N/A | N/A | 3628.9 | 5635 |
| case_2 | 30 | 0 success / 0 partial / 30 failed | 0.0% | 0.0% | 100.0% | 0.0% | 0.0% | N/A | 2436.6 | 2785 |
| case_3 | 30 | 0 success / 0 partial / 30 failed | 0.0% | 0.0% | 100.0% | 0.0% | 0.0% | N/A | 2652.0 | 4085 |

Full completion counts only `success`. Useful-result retention counts
`success` and `partial_success`; it must not be reported as full task completion.
