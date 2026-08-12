# Stage 05 Variant Comparison

- Git commit: `512de4c690b4d61ab84b194f58b689cca98f1a84`
- Plan digest: `6552751c1dcaf9453f25f69bc9f969f3159c119b6b0afdd873acd11c85164a47`
- Trials: 90 per variant; 60 attack trials per variant

| Variant | Normal success | Attack block | Full completion | Useful result | False value | Repair success | Invariants | Attack mean ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 100.0% | 100.0% | 0.0% | 0.0% | 0.0% | 0.0% | N/A | 2544.3 |
| m0 | 100.0% | 100.0% | 0.0% | 100.0% | 100.0% | 100.0% | 100.0% | 3408.1 |
| m1 | 100.0% | 100.0% | 0.0% | 100.0% | 0.0% | 100.0% | 100.0% | 3191.9 |
| m2 | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 100.0% | 100.0% | 3658.8 |

Attack metrics aggregate Case 2 and Case 3 only. Baseline latency is lower
because it aborts at the first rejected output and does not complete the remaining
trusted tool call, so it is not an equivalent end-to-end latency comparison.
Baseline's 0% false-value rate reflects that it returns no value; its useful-result
retention rate is also 0%.
