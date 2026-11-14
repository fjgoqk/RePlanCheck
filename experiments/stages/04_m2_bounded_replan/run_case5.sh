#!/usr/bin/env bash
set -euo pipefail
# 边界案例 case 5（替代工具亦失效）专用的 M2 运行入口：
# recovery manifest 指向中毒版 QuickRideVerified（返回格式错误）。
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

exec env PYTHONPATH=src .venv/bin/python \
  experiments/stages/03_deterministic_replay/run.py \
  --variant m2 \
  --case 5 \
  --recovery-manifest experiments/stages/04_m2_bounded_replan/tools/manifest_case5.json \
  --substitution QuickRideFareEstimate=QuickRideVerified \
  "$@"
