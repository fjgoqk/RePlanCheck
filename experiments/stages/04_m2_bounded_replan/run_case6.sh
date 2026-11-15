#!/usr/bin/env bash
set -euo pipefail
# 组合格 case 6（A2 + 语义毒化替代工具）：原工具格式错误 + 替代工具返回 schema 合法假值 0.01
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

exec env PYTHONPATH=src .venv/bin/python \
  experiments/stages/04_m2_bounded_replan/run_case6.py \
  --variant m2 \
  --case 6 \
  --recovery-manifest experiments/stages/04_m2_bounded_replan/tools/manifest_case6.json \
  --substitution QuickRideFareEstimate=QuickRideVerified \
  "$@"
