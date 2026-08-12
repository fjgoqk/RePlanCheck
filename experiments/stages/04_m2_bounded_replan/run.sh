#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

exec env PYTHONPATH=src .venv/bin/python \
  experiments/stages/03_deterministic_replay/run.py \
  --variant m2 \
  --recovery-manifest experiments/stages/04_m2_bounded_replan/tools/manifest.json \
  --substitution QuickRideFareEstimate=QuickRideVerified \
  "$@"
