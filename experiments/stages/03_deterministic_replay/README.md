# Stage 03: Deterministic Replay

- Status: in progress
- Objective: compare Baseline, M0, and M1 with identical fixed abstract plans.
- Deliverables: fixture schema, fixture loader, replay runner, and JSONL metadata
  for `variant`, `case_id`, `trial`, `plan_digest`, and `expected_tools`.
- Completion gate: at least 30 trials per case and variant with no planning-input
  drift.

Run one smoke trial per case:

```bash
PYTHONPATH=src .venv/bin/python \
  experiments/stages/03_deterministic_replay/run.py \
  --case all \
  --trials 1
```

Run the M1 measurement set:

```bash
PYTHONPATH=src .venv/bin/python \
  experiments/stages/03_deterministic_replay/run.py \
  --case all \
  --trials 30 \
  --output results/raw/stage03/m1-30-trials.jsonl
```

The runner freezes the abstract plan but deliberately retains ACE concrete-tool
mapping and information-flow checks. Concrete mapping variance is measured as an
experimental outcome rather than hidden by the fixture.

## M1 30-Trial Result

The first M1 measurement set completed 90/90 runs at commit `b326140` using one
plan digest. Case 1 completed successfully in 30/30 trials. Case 2 and Case 3
blocked the attack, applied a verified repair, preserved a useful trusted result,
and emitted no false fallback value in 30/30 trials each.

Case 2 and Case 3 remain `partial_success`: strict full-task completion is 0%,
while useful-result retention is 100%. Full recovery is deferred to M2.

Reviewed aggregates are in `results/processed/stage03/m1-b326140/`.

The case-study manifests also contain three unrelated legacy Gmail tools whose
schemas cannot be instantiated. `ToolManager` skips them with warnings before
the measured timer starts. QuickRide and MetroHail load correctly in all trials;
the warnings are infrastructure noise, not execution failures.
