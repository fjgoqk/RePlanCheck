# Repository Layout

RePlanCheck uses one evolving implementation and separates experimental
protocols from source snapshots.

## Versioning Rules

1. Git tags identify code checkpoints such as `replancheck-m1`.
2. `experiments/stages/` defines the protocol for each research milestone.
3. `experiments/fixtures/` stores deterministic, reviewable test inputs.
4. `results/raw/` is local-only and may contain large or sensitive records.
5. `results/processed/` contains reviewed aggregate data suitable for Git.
6. `results/figures/` contains figures generated from processed data.

Do not duplicate the full source tree inside a stage directory. A stage must
reference a commit or tag and include enough configuration to replay it.

## Naming Convention

- stage directories: `NN_short_name`;
- raw records: `<stage>-<case>-<timestamp>.jsonl`;
- processed tables: `<comparison>-summary.csv`;
- figures: `<metric>-<comparison>.pdf`;
- Git tags: `replancheck-mN` or `paper-evaluation-vN`.
