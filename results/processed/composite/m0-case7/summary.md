# WP2 Composite M0 Case 7

- Source: `results/raw/composite/m0-case7.jsonl`
- Git commit: `5ab02678491ec414e66fed2424d7c89013abde64`
- Plan digest: `5177dc4f2eafba1154f43d286ef9b7d46e25f8d25dacdf7105e5813d3bf4a8c9`
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
| Poisoned source markers | 60 |

Full completion counts only `success`. Useful-result retention counts `success` and
`partial_success`, matching `analyze_replay.py`. Source-marker counts are occurrences
across step provenance lists; substitute counts exclude poisoned markers.
