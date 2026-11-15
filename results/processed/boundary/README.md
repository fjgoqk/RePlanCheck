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

## Case 6 (2026-11-15, composed A2 cell)

Composed attacker cell answering the review question: what happens when the
substitute is poisoned with a *schema-valid* semantic fake (A2: original tool
malformed-poisoned + substitute returns the fake fare 0.01)?

- Assets: `benchmarks/case_studies/case_6/` (case manifest = case 5's);
  recovery manifest `experiments/stages/04_m2_bounded_replan/tools/manifest_case6.json`;
  runner `experiments/stages/04_m2_bounded_replan/run_case6.sh` (run_case6.py).
- Command: `./experiments/stages/04_m2_bounded_replan/run_case6.sh --trials 30 --output results/raw/boundary/m2-case6.jsonl --overwrite`

### Result (M2, n = 30)

| Metric | Value |
|---|---|
| full completion | 30/30 |
| useful retention | 30/30 |
| false value (final_output == 0.01) | **30/30** |
| completed substitution | 30/30 |
| invariant pass | 30/30 |

### Finding 3 (Case 6)

The composed A2-semantic cell confirms the mechanism's detection boundary
empirically: the poisoned substitute's schema-valid fake fare passes the
adapter's output validation and re-enters the plan as a business result, so the
task "completes" (30/30) while the false value propagates (30/30) — with every
checked bookkeeping invariant passing. The zero-false-value claim therefore
holds only against schema-detectable failures (Cases 2/3/5); a semantic fake
from the substitute lies outside the checked surface, exactly as Case 4 shows
for the original tool. This cell is reported in the paper's Evaluation and
bounds the threat-model claims.
