# Boundary Cases: Case 4 (Semantic Fake) & Case 5 (Substitute Failure)

**Date**: 2026-11-15
**Scope**: Two adversarial boundary cases added to the deterministic-replay suite,
bringing the total to 5 cases × 4 variants × 30 trials = 600 runs.
All runs share the same git commit, plan digest, and frozen inputs as the main cases.

## Reproduction

```bash
# case 4 — semantic fake value (schema-valid, tampered fare)
PYTHONPATH=src .venv/bin/python experiments/stages/03_deterministic_replay/run.py \
  --variant {baseline|m0|m1} --case 4 --trials 30 \
  --output results/raw/boundary/{variant}-case4.jsonl --overwrite
experiments/stages/04_m2_bounded_replan/run.sh --case 4 --trials 30 \
  --output results/raw/boundary/m2-case4.jsonl --overwrite

# case 5 — substitute tool also fails (poisoned recovery manifest)
PYTHONPATH=src .venv/bin/python experiments/stages/03_deterministic_replay/run.py \
  --variant {baseline|m0|m1} --case 5 --trials 30 \
  --output results/raw/boundary/{variant}-case5.jsonl --overwrite
experiments/stages/04_m2_bounded_replan/run_case5.sh --trials 30 \
  --output results/raw/boundary/m2-case5.jsonl --overwrite
```

## Results (per-case, n=30 each)

| Variant | C4 full completion | C4 false value | C5 full completion | C5 useful retention | C5 false value |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline | 30/30 | 30/30 | 0/30 | 0/30 | 0/30 |
| m0 | 30/30 | 30/30 | 0/30 | 30/30 | 30/30 |
| m1 | 30/30 | 30/30 | 0/30 | 30/30 | 0/30 |
| m2 (RePlanCheck) | 30/30 | 30/30 | 0/30 | 30/30 | 0/30 |

### Metric definitions

- **Full completion**: `outcome.status == "success"`.
- **Useful retention**: ≥1 tool result with `status == "success"`.
- **False value (semantic)**: `final_output ∈ {0.0, 0.01}` — i.e., the synthesized
  default (M0) or the tampered fare (case 4). This definition deliberately differs
  from `analyze_replay.py`'s false-value metric, which detects the
  *rejected-but-non-null* pattern and cannot see schema-valid semantic poisoning.

### Findings

1. **Case 4**: schema validation is transparent to semantic fraud. All four
   variants complete the task and propagate the fake value — including M2, whose
   substitution never triggers because the poisoned output passes validation.
   This is the failure mode that motivates the WP4 adaptive-attacker (A1/A2)
   evaluation and the "do-not-recover" option.
2. **Case 5**: when the pre-authorized substitute also fails, M2 fails closed:
   0/30 full completion, 0/30 false values, 30/30 useful retention, explicit
   `partial_success` degradation — a mechanism-level contrast to baseline
   fail-stop (0/30 retention) and to M0's silent fake (30/30 false values).

## Known limitation

`experiments/analysis/analyze_replay.py` does not yet cover semantic poisoning:
its `false_value_rate` is N/A for case 4/5 (attack-case set is `{case_2, case_3}`).
Extending it requires a value-aware oracle (compare tool output against ground
truth), tracked as follow-up work.
