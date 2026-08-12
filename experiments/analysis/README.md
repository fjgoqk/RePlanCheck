# Experiment Analysis

Analysis code will consume JSONL records and produce reviewed tables under
`results/processed/` and figures under `results/figures/`.

Required metrics:

- attack-block rate;
- task-completion rate;
- false-value rate;
- repair-success rate;
- invariant-pass rate;
- mean and P95 latency.

Analyze a deterministic replay file:

```bash
PYTHONPATH=. .venv/bin/python experiments/analysis/analyze_replay.py \
  results/raw/stage03/m1-30-trials-80496ba.jsonl \
  --output-dir results/processed/stage03/m1-80496ba
```

Compare reviewed baseline, M0, and M1 summaries from the same execution
commit:

```bash
PYTHONPATH=src .venv/bin/python experiments/analysis/compare_variants.py \
  results/processed/stage03/baseline-80496ba/summary.json \
  results/processed/stage03/m0-80496ba/summary.json \
  results/processed/stage03/m1-80496ba/summary.json \
  --output-dir results/processed/stage03/comparison-80496ba
```
