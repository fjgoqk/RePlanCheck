#!/usr/bin/env python3
"""Verify every number in Tables 2--4 of the RePlanCheck paper from the raw logs.

Run from the repository root:

    PYTHONPATH=src .venv/bin/python analysis/verify_paper_tables.py

Exit code 0 means every asserted cell matched the raw JSONL. Any mismatch is
printed and makes the script exit 1.

Definitions follow the paper (Section 4.2):
  * full-task completion   -- outcome.status == "success"
  * useful-result retention -- outcome.status in {"success", "partial_success"}
  * false value             -- outcome.final_output is numeric and differs from the
                               fixture ground-truth fare 49.2 (MetroHail's 33.0 is
                               checked as a second ground truth when present)
  * malformed rejected      -- the run recorded at least one failure

Note: experiments/analysis/analyze_replay.py computes a narrower, mechanism-side
notion of a false value (a rejected result carrying a value, or an unresolved
failure with a non-null final output). That definition cannot see a schema-valid
poisoned value, which is why Case 4 is 0 there and 30/30 here. The paper's tables
use the ground-truth definition above; both are reported by this script.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

GROUND_TRUTH_QUICKRIDE = 49.2
GROUND_TRUTH_METROHAIL = 33.0
# Each tool is compared against its own ground truth; the plan's final answer is
# the QuickRide fare compared in the scenario.
TOOL_GROUND_TRUTH = {
    "QuickRide": GROUND_TRUTH_QUICKRIDE,
    "QuickRideVerified": GROUND_TRUTH_QUICKRIDE,
    "MetroHail": GROUND_TRUTH_METROHAIL,
}
EPS = 1e-9

STAGE05_RAW = ROOT / "results/raw/stage05/512de4c"
BOUNDARY_RAW = ROOT / "results/raw/boundary"

ATTACK_CASES = ("case_2", "case_3")
VARIANTS = ("baseline", "m0", "m1", "m2")


# --------------------------------------------------------------------------- #
# loading and per-cell summary
# --------------------------------------------------------------------------- #
def load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"missing raw log: {path}")
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len({r["run_id"] for r in records}) != len(records):
        raise ValueError(f"duplicate run ids in {path}")
    return records


def percentile(values: list[int], fraction: float) -> int:
    """Same definition as experiments/analysis/analyze_replay.py: nearest-rank."""
    ordered = sorted(values)
    return ordered[math.ceil(fraction * len(ordered)) - 1]


def is_false_value(outcome: dict[str, Any]) -> bool:
    """Paper definition: a business result differing from the fixture ground truth."""
    final = outcome.get("final_output")
    if isinstance(final, (int, float)) and abs(float(final) - GROUND_TRUTH_QUICKRIDE) > EPS:
        return True
    for tool, result in (outcome.get("tool_results") or {}).items():
        expected = TOOL_GROUND_TRUTH.get(tool)
        if expected is None:
            continue
        value = result.get("value")
        if not isinstance(value, dict):
            continue
        fare = value.get("fare")
        if isinstance(fare, (int, float)) and abs(float(fare) - expected) > EPS:
            return True
    return False


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(r["outcome"]["status"] for r in records)
    durations = [r["duration_ms"] for r in records]
    return {
        "n": len(records),
        "success": statuses.get("success", 0),
        "partial": statuses.get("partial_success", 0),
        "failed": statuses.get("failed", 0),
        "false_values": sum(is_false_value(r["outcome"]) for r in records),
        "rejected_runs": sum(bool(r["outcome"]["failures"]) for r in records),
        "mean_ms": round(sum(durations) / len(durations), 1),
        "min_ms": min(durations),
        "p95_ms": percentile(durations, 0.95),
    }


def by_case(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[record["case_id"]].append(record)
    return {case: summarize(rows) for case, rows in grouped.items()}


def attack_pool(records: list[dict[str, Any]]) -> dict[str, Any]:
    return summarize([r for r in records if r["case_id"] in ATTACK_CASES])


# --------------------------------------------------------------------------- #
# expected values, transcribed from the manuscript
# --------------------------------------------------------------------------- #
# Table 2 -- main comparison. (normal success, malformed rejected, attack completion,
# attack retention, attack false values), all over n = 30 normal / n = 60 attack.
TABLE_2 = {
    "baseline": (30, 60, 0, 0, 0),
    "m0": (30, 60, 0, 60, 60),
    "m1": (30, 60, 0, 60, 0),
    "m2": (30, 60, 60, 60, 0),
}

# Table 3 -- attack-scenario latency, pooled over Cases 2-3 (n = 60).
TABLE_3 = {
    "baseline": (2544.3, 2119, 3196),
    "m0": (3408.1, 2926, 3724),
    "m1": (3191.9, 2945, 3518),
    "m2": (3658.8, 3245, 4067),
}

# Table 4 -- boundary cells. (completion, retention, false values) over n = 30.
TABLE_4 = {
    ("case_4", "baseline"): (30, 30, 30),
    ("case_4", "m0"): (30, 30, 30),
    ("case_4", "m1"): (30, 30, 30),
    ("case_4", "m2"): (30, 30, 30),
    ("case_5", "baseline"): (0, 0, 0),
    ("case_5", "m0"): (0, 30, 30),
    ("case_5", "m1"): (0, 30, 0),
    ("case_5", "m2"): (0, 30, 0),
    ("case_6", "m2"): (30, 30, 30),
}


# --------------------------------------------------------------------------- #
# checks
# --------------------------------------------------------------------------- #
def main() -> int:
    failures: list[str] = []
    results: list[tuple[str, str, str]] = []

    def check(label: str, actual: Any, expected: Any) -> None:
        ok = actual == expected
        results.append((label, str(actual), str(expected)))
        if not ok:
            failures.append(f"{label}: expected {expected}, got {actual}")

    stage05 = {v: load_records(STAGE05_RAW / f"{v}.jsonl") for v in VARIANTS}

    # --- Table 2 ----------------------------------------------------------- #
    total_runs = 0
    for variant in VARIANTS:
        records = stage05[variant]
        total_runs += len(records)
        cells = by_case(records)
        attack = attack_pool(records)
        normal, rejected, completion, retained, false_values = TABLE_2[variant]
        check(f"Table 2 {variant} normal success", cells["case_1"]["success"], normal)
        check(f"Table 2 {variant} malformed rejected", attack["rejected_runs"], rejected)
        check(f"Table 2 {variant} attack completion", attack["success"], completion)
        check(f"Table 2 {variant} attack retention", attack["success"] + attack["partial"], retained)
        check(f"Table 2 {variant} attack false values", attack["false_values"], false_values)

    check("run count, main evaluation (4 variants x 3 cases x 30)", total_runs, 360)

    # --- Table 3 ----------------------------------------------------------- #
    for variant in VARIANTS:
        attack = attack_pool(stage05[variant])
        mean, minimum, p95 = TABLE_3[variant]
        check(f"Table 3 {variant} mean ms", attack["mean_ms"], mean)
        check(f"Table 3 {variant} min ms", attack["min_ms"], minimum)
        check(f"Table 3 {variant} p95 ms", attack["p95_ms"], p95)

    # --- Table 4 ----------------------------------------------------------- #
    boundary: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for variant in VARIANTS:
        for case in ("case_4", "case_5"):
            slug = case.replace("case_", "case")  # raw logs use case4/case5
            boundary[(case, variant)] = load_records(BOUNDARY_RAW / f"{variant}-{slug}.jsonl")
    boundary[("case_6", "m2")] = load_records(BOUNDARY_RAW / "m2-case6.jsonl")

    boundary_runs = sum(len(rows) for rows in boundary.values())
    for (case, variant), expected in TABLE_4.items():
        summary = summarize(boundary[(case, variant)])
        completion, retention, false_values = expected
        check(f"Table 4 {case} {variant} completion", summary["success"], completion)
        check(f"Table 4 {case} {variant} retention", summary["success"] + summary["partial"], retention)
        check(f"Table 4 {case} {variant} false values", summary["false_values"], false_values)

    # 4 variants x Cases 4-5 x 30 = 240 boundary runs, plus 30 for Case 6.
    check("run count, boundary cells (4 x 2 x 30 + 30)", boundary_runs, 270)
    check("run count, total (360 + 240 main, plus 30 Case 6)", total_runs + 240 + 30, 630)

    # --- report ------------------------------------------------------------ #
    width = max(len(label) for label, _, _ in results)
    for label, actual, expected in results:
        flagged = "" if actual == expected else "   <-- MISMATCH"
        print(f"{label:<{width}}  got {actual:>10}  expected {expected:>10}{flagged}")

    print()
    if failures:
        print(f"FAIL: {len(failures)} of {len(results)} assertions did not match")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"PASS: all {len(results)} assertions match the raw logs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
