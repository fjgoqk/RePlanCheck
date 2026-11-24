# WP2 Composite M1 Case 8

- Source: `results/raw/composite/m1-case8.jsonl`
- Git commit: `5ab02678491ec414e66fed2424d7c89013abde64`
- Plan digest: `052f9e8acfcf3221cb56672b79ff43fd7515a3def98bf915b0bc2830f59fd5b7`
- Trials: 30

| Metric | Count | Rate |
| --- | ---: | ---: |
| Full task completion | 0 | 0.0% |
| Useful-result retention | 30 | 100.0% |
| False-value propagation | 0 | 0.0% |

| Budget and source evidence | Count |
| --- | ---: |
| Recovery budget consumed | 0 |
| Budget exhausted runs | 0 |
| Explicit degradation events | 30 |
| Recovery substitution events | 0 |
| Substitute source markers | 0 |
| Poisoned source markers | 0 |

Full completion counts only `success`. Useful-result retention counts `success` and
`partial_success`, matching `analyze_replay.py`. Source-marker counts are occurrences
across step provenance lists; substitute counts exclude poisoned markers.
