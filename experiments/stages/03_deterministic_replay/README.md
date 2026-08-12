# Stage 03: Deterministic Replay

- Status: next
- Objective: compare Baseline, M0, and M1 with identical fixed abstract plans.
- Deliverables: fixture schema, fixture loader, replay runner, and JSONL metadata
  for `variant`, `case_id`, `trial`, `plan_digest`, and `expected_tools`.
- Completion gate: at least 30 trials per case and variant with no planning-input
  drift.
