import argparse
import csv
import json
from pathlib import Path
from typing import Any

EXPECTED_VARIANTS = {"baseline", "m0", "m1"}
ATTACK_CASES = {"case_2", "case_3"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare reviewed Stage 03 variant summaries")
    parser.add_argument("inputs", type=Path, nargs=3)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/processed/stage03/comparison-80496ba"),
    )
    return parser.parse_args()


def load_summaries(paths: list[Path]) -> list[dict[str, Any]]:
    summaries = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    variants = {summary["variant"] for summary in summaries}
    if variants != EXPECTED_VARIANTS:
        raise ValueError(f"Expected variants {sorted(EXPECTED_VARIANTS)}, found {sorted(variants)}")
    if len({summary["git_commit"] for summary in summaries}) != 1:
        raise ValueError("Variant summaries use different Git commits")
    if len({summary["plan_digest"] for summary in summaries}) != 1:
        raise ValueError("Variant summaries use different plan digests")
    if any(summary["total_trials"] != 90 for summary in summaries):
        raise ValueError("Each variant must contain exactly 90 trials")
    return sorted(summaries, key=lambda summary: ["baseline", "m0", "m1"].index(summary["variant"]))


def _count(cases: list[dict[str, Any]], rate: str) -> int:
    return sum(round(case[rate] * case["trials"]) for case in cases if case[rate] is not None)


def compare(summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for summary in summaries:
        cases = {case["case_id"]: case for case in summary["cases"]}
        if set(cases) != {"case_1", *ATTACK_CASES}:
            raise ValueError(f"Variant {summary['variant']} does not contain all three cases")

        normal = cases["case_1"]
        attacks = [cases[case_id] for case_id in sorted(ATTACK_CASES)]
        attack_trials = sum(case["trials"] for case in attacks)
        invariant_trials = sum(case["trials"] for case in attacks if case["invariant_pass_rate"] is not None)

        rows.append(
            {
                "variant": summary["variant"],
                "normal_success_rate": normal["success"] / normal["trials"],
                "attack_trials": attack_trials,
                "attack_block_rate": _count(attacks, "attack_block_rate") / attack_trials,
                "useful_result_retention_rate": _count(attacks, "useful_result_retention_rate") / attack_trials,
                "false_value_rate": _count(attacks, "false_value_rate") / attack_trials,
                "repair_success_rate": _count(attacks, "repair_success_rate") / attack_trials,
                "invariant_pass_rate": (
                    _count(attacks, "invariant_pass_rate") / invariant_trials if invariant_trials else None
                ),
                "attack_mean_latency_ms": round(
                    sum(case["mean_latency_ms"] * case["trials"] for case in attacks) / attack_trials,
                    1,
                ),
            }
        )
    return rows


def write_outputs(summaries: list[dict[str, Any]], rows: list[dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "schema_version": "1.0",
        "git_commit": summaries[0]["git_commit"],
        "plan_digest": summaries[0]["plan_digest"],
        "trials_per_variant": summaries[0]["total_trials"],
        "attack_trials_per_variant": rows[0]["attack_trials"],
        "variants": rows,
    }
    (output_dir / "comparison.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    with (output_dir / "comparison.csv").open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    def rate(value: float | None) -> str:
        return "N/A" if value is None else f"{value:.1%}"

    lines = [
        "# Stage 03 Variant Comparison",
        "",
        f"- Git commit: `{metadata['git_commit']}`",
        f"- Plan digest: `{metadata['plan_digest']}`",
        f"- Trials: {metadata['trials_per_variant']} per variant; {metadata['attack_trials_per_variant']} attack trials per variant",
        "",
        "| Variant | Normal success | Attack block | Useful result | False value | Repair success | Invariants | Attack mean ms |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row['variant']} | {rate(row['normal_success_rate'])} | {rate(row['attack_block_rate'])} | "
            f"{rate(row['useful_result_retention_rate'])} | {rate(row['false_value_rate'])} | "
            f"{rate(row['repair_success_rate'])} | {rate(row['invariant_pass_rate'])} | "
            f"{row['attack_mean_latency_ms']:.1f} |"
        )
    lines.extend(
        [
            "",
            "Attack metrics aggregate Case 2 and Case 3 only. Baseline latency is lower",
            "because it aborts at the first rejected output and does not complete the remaining",
            "trusted tool call, so it is not an equivalent end-to-end latency comparison.",
            "Baseline's 0% false-value rate reflects that it returns no value; its useful-result",
            "retention rate is also 0%.",
        ]
    )
    (output_dir / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    summaries = load_summaries(args.inputs)
    rows = compare(summaries)
    write_outputs(summaries, rows, args.output_dir)
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
