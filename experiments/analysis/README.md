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
  results/raw/stage03/m1-30-trials-b326140.jsonl \
  --output-dir results/processed/stage03/m1-b326140
```
