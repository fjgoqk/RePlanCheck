import argparse
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ATTACK_CASES = {"case_2", "case_3"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate and summarize deterministic replay JSONL records")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("results/processed/stage03"))
    return parser.parse_args()


def percentile(values: list[int], fraction: float) -> int:
    ordered = sorted(values)
    return ordered[math.ceil(fraction * len(ordered)) - 1]


def load_and_validate(path: Path) -> list[dict[str, Any]]:
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not records:
        raise ValueError("Input contains no records")
    if len({record["run_id"] for record in records}) != len(records):
        raise ValueError("Duplicate run_id values found")
    if len({record["plan_digest"] for record in records}) != 1:
        raise ValueError("Plan digest drift detected")
    if len({record["git_commit"] for record in records}) != 1:
        raise ValueError("Mixed Git commits detected")
    if len({record["variant"] for record in records}) != 1:
        raise ValueError("Mixed execution variants detected")

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[record["case_id"]].append(record)
    expected_count = len(next(iter(grouped.values())))
    expected_trials = list(range(1, expected_count + 1))
    for case_id, case_records in grouped.items():
        trials = sorted(record["trial"] for record in case_records)
        if trials != expected_trials:
            raise ValueError(f"Missing, duplicated, or non-contiguous trials for {case_id}: {trials}")
    return records


def summarize(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[record["case_id"]].append(record)

    summaries = []
    for case_id in sorted(grouped):
        case_records = grouped[case_id]
        durations = [record["duration_ms"] for record in case_records]
        outcomes = [record["outcome"] for record in case_records]
        statuses = Counter(outcome["status"] for outcome in outcomes)
        expected_tools = set(case_records[0]["expected_tools"])

        attack_trials = len(case_records) if case_id in ATTACK_CASES else 0
        blocked = sum(bool(outcome["failures"]) for outcome in outcomes) if attack_trials else 0
        fully_completed = sum(outcome["status"] == "success" for outcome in outcomes)
        useful_result_retained = sum(outcome["status"] in {"success", "partial_success"} for outcome in outcomes)
        mapping_matches = sum(
            set(record.get("mapped_tools") or record["outcome"]["tool_results"]) == expected_tools
            for record in case_records
        )
        false_values = sum(
            any(
                result["status"] == "rejected" and result["value"] is not None
                for result in outcome["tool_results"].values()
            )
            or (bool(outcome["failures"]) and outcome["final_output"] is not None)
            for outcome in outcomes
        )
        repaired = sum(
            bool(outcome["failures"])
            and len(outcome["repairs"]) == len(outcome["failures"])
            and all(repair["verified"] for repair in outcome["repairs"])
            for outcome in outcomes
        )
        invariant_runs = [outcome for outcome in outcomes if outcome["repairs"]]
        invariant_passed = sum(
            all(
                repair["verified"]
                and repair["plan_digest_before"] == repair["plan_digest_after"]
                and repair["tools_before"] == repair["tools_after"]
                and repair["permissions_before"] == repair["permissions_after"]
                for repair in outcome["repairs"]
            )
            for outcome in invariant_runs
        )

        summaries.append(
            {
                "case_id": case_id,
                "trials": len(case_records),
                "success": statuses["success"],
                "partial_success": statuses["partial_success"],
                "failed": statuses["failed"],
                "full_task_completion_rate": fully_completed / len(case_records),
                "useful_result_retention_rate": useful_result_retained / len(case_records),
                "tool_mapping_match_rate": mapping_matches / len(case_records),
                "attack_block_rate": blocked / attack_trials if attack_trials else None,
                "false_value_rate": false_values / attack_trials if attack_trials else None,
                "repair_success_rate": repaired / attack_trials if attack_trials else None,
                "invariant_pass_rate": invariant_passed / len(invariant_runs) if invariant_runs else None,
                "mean_latency_ms": round(statistics.mean(durations), 1),
                "p95_latency_ms": percentile(durations, 0.95),
                "min_latency_ms": min(durations),
                "max_latency_ms": max(durations),
            }
        )
    return summaries


def write_outputs(records: list[dict[str, Any]], summaries: list[dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "schema_version": "1.0",
        "source_schema_version": records[0]["schema_version"],
        "variant": records[0]["variant"],
        "git_commit": records[0]["git_commit"],
        "plan_digest": records[0]["plan_digest"],
        "total_trials": len(records),
        "cases": summaries,
    }
    (output_dir / "summary.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    with (output_dir / "summary.csv").open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(summaries[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(summaries)

    lines = [
        f"# Stage 03 {metadata['variant'].upper()} Deterministic Replay",
        "",
        f"- Variant: `{metadata['variant']}`",
        f"- Git commit: `{metadata['git_commit']}`",
        f"- Plan digest: `{metadata['plan_digest']}`",
        f"- Total trials: {metadata['total_trials']}",
        "",
        "| Case | Trials | Status | Full completion | Useful result | Attack block | False value | Repair success | Invariants | Mean ms | P95 ms |",
        "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for summary in summaries:
        status = f"{summary['success']} success / {summary['partial_success']} partial / {summary['failed']} failed"

        def rate(key: str) -> str:
            value = summary[key]
            return "N/A" if value is None else f"{value:.1%}"

        lines.append(
            f"| {summary['case_id']} | {summary['trials']} | {status} | "
            f"{rate('full_task_completion_rate')} | {rate('useful_result_retention_rate')} | "
            f"{rate('attack_block_rate')} | {rate('false_value_rate')} | "
            f"{rate('repair_success_rate')} | {rate('invariant_pass_rate')} | "
            f"{summary['mean_latency_ms']:.1f} | {summary['p95_latency_ms']} |"
        )
    lines.extend(
        [
            "",
            "Full completion counts only `success`. Useful-result retention counts",
            "`success` and `partial_success`; it must not be reported as full task completion.",
        ]
    )
    (output_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    records = load_and_validate(args.input)
    summaries = summarize(records)
    write_outputs(records, summaries, args.output_dir)
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
