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
