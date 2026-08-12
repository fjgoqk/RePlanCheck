#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "Tracked worktree changes found. Commit them before the final evaluation." >&2
  exit 1
fi

MODE=()
if [[ "${1:-}" == "--resume" ]]; then
  MODE=(--resume)
  shift
fi
if [[ $# -ne 0 ]]; then
  echo "Usage: $0 [--resume]" >&2
  exit 2
fi

COMMIT="$(git rev-parse HEAD)"
SHORT_COMMIT="$(git rev-parse --short HEAD)"
RAW_DIR="results/raw/stage05/${SHORT_COMMIT}"
PROCESSED_DIR="results/processed/stage05/${SHORT_COMMIT}"
FIGURE_DIR="results/figures/stage05/${SHORT_COMMIT}"

mkdir -p "$RAW_DIR" "$PROCESSED_DIR" "$FIGURE_DIR"

for variant in baseline m0 m1; do
  PYTHONPATH=src .venv/bin/python \
    experiments/stages/03_deterministic_replay/run.py \
    --variant "$variant" \
    --case all \
    --trials 30 \
    --output "$RAW_DIR/${variant}.jsonl" \
    "${MODE[@]}"
done

./experiments/stages/04_m2_bounded_replan/run.sh \
  --case all \
  --trials 30 \
  --output "$RAW_DIR/m2.jsonl" \
  "${MODE[@]}"

for variant in baseline m0 m1 m2; do
  PYTHONPATH=src .venv/bin/python experiments/analysis/analyze_replay.py \
    "$RAW_DIR/${variant}.jsonl" \
    --output-dir "$PROCESSED_DIR/$variant"
done

PYTHONPATH=src .venv/bin/python experiments/analysis/compare_variants.py \
  "$PROCESSED_DIR/baseline/summary.json" \
  "$PROCESSED_DIR/m0/summary.json" \
  "$PROCESSED_DIR/m1/summary.json" \
  "$PROCESSED_DIR/m2/summary.json" \
  --include-m2 \
  --output-dir "$PROCESSED_DIR/comparison"

PYTHONPATH=src .venv/bin/python experiments/analysis/generate_comparison_figures.py \
  "$PROCESSED_DIR/comparison/comparison.json" \
  --output-dir "$FIGURE_DIR"

printf 'Stage 05 complete\nCommit: %s\nResults: %s\nFigures: %s\n' \
  "$COMMIT" "$PROCESSED_DIR" "$FIGURE_DIR"
