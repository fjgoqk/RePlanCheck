# WP2 Composite M0 Case 9

- Source: `results/raw/composite/m0-case9.jsonl`
- Git commit: `5ab02678491ec414e66fed2424d7c89013abde64`
- Plan digest: `6d6c951a3b70c07fb3cf527cc9122e68c5263b01ee26bee274cfedf0a64dd96f`
- Trials: 30

| Metric | Count | Rate |
| --- | ---: | ---: |
| Full task completion | 0 | 0.0% |
| Useful-result retention | 30 | 100.0% |
| False-value propagation | 30 | 100.0% |

| Budget and source evidence | Count |
| --- | ---: |
| Recovery budget consumed | 0 |
| Budget exhausted runs | 0 |
| Explicit degradation events | 0 |
| Recovery substitution events | 0 |
| Substitute source markers | 0 |
| Poisoned source markers | 0 |

Full completion counts only `success`. Useful-result retention counts `success` and
`partial_success`, matching `analyze_replay.py`. Source-marker counts are occurrences
across step provenance lists; substitute counts exclude poisoned markers.
