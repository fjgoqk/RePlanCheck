# Experiments

Each stage directory records one research milestone. A stage should contain its
objective, code reference, protocol, expected artifacts, and completion gate.

```text
fixtures/                       deterministic plans and inputs
stages/00_ace_baseline/         unrepaired ACE behavior
stages/01_m0_local_recovery/    verified reject-and-resume
stages/02_m1_outcome_logging/   trusted outcomes and JSONL records
stages/03_deterministic_replay/ identical cross-variant inputs
stages/04_m2_bounded_replan/    verified bounded replanning
stages/05_final_evaluation/     repeated comparison and paper tables
analysis/                       aggregation, statistics, and figures
```

Raw logs are not committed by default. Commit reviewed fixtures, experiment
configuration, analysis code, aggregate tables, and figures needed to reproduce
paper claims.
