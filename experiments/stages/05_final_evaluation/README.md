# Stage 05: Final Evaluation

- Status: implementation complete; same-commit measurement pending
- Objective: compare ACE Baseline, M0, M1, and M2 across fixed attacks and normal
  workloads.
- Deliverables: aggregate CSV files, statistical summaries, paper figures, and
  a complete reproduction command.
- Reporting rule: include all failed trials and planning variance.

## Controlled Comparison

The final comparison runs all four execution policies from one clean Git
commit. Every variant uses the same reviewed abstract-plan fixture, query,
case-study manifests, model settings, plan digest, and 30 trials per case.
Concrete mapping remains active and is measured independently. Only the M2
policy receives the separate, pre-approved recovery manifest.

The experiment therefore contains 360 runs:

- 4 execution variants: Baseline, M0, M1, and M2;
- 3 cases per variant: one normal and two attack cases;
- 30 trials per case.

Raw JSONL records are ignored by Git. Reviewed per-variant summaries, the
four-variant comparison, and generated SVG figures are committed only after
record-count, commit, plan-digest, and trial-continuity checks pass.

## Run

Commit the Stage 05 runner before starting, then execute:

```bash
./experiments/stages/05_final_evaluation/run.sh
```

If infrastructure interruption stops the run, use:

```bash
./experiments/stages/05_final_evaluation/run.sh --resume
```

Resume mode validates schema version, execution variant, Git commit, plan
digest, model settings, recovery configuration, and completed trial numbers
before continuing.

## Outputs

For commit `<commit>` the script creates:

- `results/raw/stage05/<commit>/{baseline,m0,m1,m2}.jsonl`
- `results/processed/stage05/<commit>/` with per-variant and comparison tables
- `results/figures/stage05/<commit>/effectiveness.svg`
- `results/figures/stage05/<commit>/attack_latency.svg`

The effectiveness figure reports attack blocking, strict full-task completion,
useful-result retention, false-value rate, and invariant preservation. The
latency figure is reported separately because Baseline aborts before equivalent
end-to-end work completes.
