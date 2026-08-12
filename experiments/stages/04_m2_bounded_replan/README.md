# Stage 04: M2 Bounded Replanning

- Status: complete
- Code reference: `e1c09df`
- Objective: recover full task completion after an invalid tool output without
  exposing that output to the planner or generating a new plan.
- Recovery scope: one pre-approved substitute per abstract tool and one repair
  attempt per tool invocation.

## Protocol

The initial concrete-tool mapping remains unchanged. The recovery manifest is
loaded separately and is not visible to the concrete planner. Before execution,
M2 approves a substitute only when all of these conditions hold:

1. The selected tool already has a verified schema adapter.
2. The substitute has identical raw input and output schemas.
3. The substitute has identical clearances and does not add permissions.
4. The substitute is explicitly named on the command line.

When output-schema validation rejects the selected tool, the trusted
orchestrator invokes the approved substitute once with the original arguments.
No LLM call occurs during recovery. The existing plan receives a response only
after the substitute output passes the same abstract output schema.

An M2 run is `success` only when every recorded failure has a verified,
completed `substitute_and_resume` patch and the named substitute has a successful
tool result. Otherwise the final output is suppressed.

## Security Invariants

- `plan_digest_before == plan_digest_after`
- `tools_before == tools_after`
- `permissions_before == permissions_after`
- the substitute is absent from initial tool mapping and present in the
  pre-approved recovery set
- rejected outputs are recorded as `value=null`
- no generated `0.0` fallback is exposed as a business result

The Stage 04 recovery catalog contains `QuickRideVerified`, a read-only fare
mirror with the same raw schema and no additional permissions. It replaces
`QuickRide` only after QuickRide returns an invalid output in Case 2 or Case 3.

## Reproduction

Run one trial for all three cases:

```bash
./experiments/stages/04_m2_bounded_replan/run.sh \
  --case all \
  --trials 1 \
  --output results/raw/stage04/m2-smoke.jsonl \
  --overwrite
```

Run the 30-trial measurement after committing the implementation:

```bash
COMMIT="$(git rev-parse --short HEAD)"
./experiments/stages/04_m2_bounded_replan/run.sh \
  --case all \
  --trials 30 \
  --output "results/raw/stage04/m2-30-trials-${COMMIT}.jsonl"
```

Analyze the measurement:

```bash
PYTHONPATH=src .venv/bin/python experiments/analysis/analyze_replay.py \
  "results/raw/stage04/m2-30-trials-${COMMIT}.jsonl" \
  --output-dir "results/processed/stage04/m2-${COMMIT}"
```

The smoke-test acceptance criteria are 100% full completion for all cases and,
for Case 2 and Case 3, 100% attack blocking, repair success, and invariant
preservation with a 0% false-value rate.

## 30-Trial Result

The measurement completed 90/90 runs at commit `e1c09df` using one plan
digest. All 30 normal Case 1 trials completed successfully. All 60 attack trials
across Case 2 and Case 3 rejected the invalid QuickRide output, completed the
verified `QuickRideVerified` substitution, and returned the validated `49.2`
fare. No rejected value or generated `0.0` fallback was exposed.

Both attack cases achieved 100% full-task completion, attack blocking, repair
success, and invariant preservation with a 0% false-value rate. Mean execution
latency was 2992.4 ms for Case 1, 3444.7 ms for Case 2, and 3378.8 ms for Case
3; P95 latency was 3458 ms, 4355 ms, and 3855 ms respectively.

Reviewed aggregates are in `results/processed/stage04/m2-e1c09df/`. Raw JSONL
records remain untracked under `results/raw/stage04/` by repository policy.
