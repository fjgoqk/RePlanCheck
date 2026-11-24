"""Validate and summarize the deterministic WP2 composite experiment records."""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


VARIANT_ORDER = ("baseline", "m0", "m1", "m2")
CASE_ORDER = ("case_7", "case_8", "case_9")
EXPECTED_TRIALS = 30
DEGRADED_EVENT = "recovery_degraded"
SUBSTITUTED_EVENT = "recovery_substituted"

SCRIPT_PATH = Path(__file__).resolve()
REPOSITORY_ROOT = SCRIPT_PATH.parents[2]
RAW_DIR = REPOSITORY_ROOT / "results" / "raw" / "composite"
OUTPUT_DIR = REPOSITORY_ROOT / "results" / "processed" / "composite"


class CompositeSummaryError(ValueError):
    """Report invalid input data or a failed composite-experiment assertion."""


def _source_labels(record: dict[str, Any]) -> list[str]:
    provenance = record.get("provenance")
    if not isinstance(provenance, dict):
        raise CompositeSummaryError(f"{record.get('run_id', '<unknown>')}: provenance must be an object")
    labels: list[str] = []
    for step_id, step_labels in provenance.items():
        if not isinstance(step_labels, list) or not all(isinstance(label, str) for label in step_labels):
            raise CompositeSummaryError(
                f"{record.get('run_id', '<unknown>')}: provenance for {step_id} must be a list of strings"
            )
        labels.extend(step_labels)
    return labels


def _event_types(record: dict[str, Any]) -> list[str]:
    events = record.get("events")
    if not isinstance(events, list):
        raise CompositeSummaryError(f"{record.get('run_id', '<unknown>')}: events must be a list")
    sequences = [event.get("sequence") for event in events]
    if sequences != list(range(1, len(events) + 1)):
        raise CompositeSummaryError(
            f"{record.get('run_id', '<unknown>')}: event sequence is not contiguous: {sequences}"
        )
    event_types = [event.get("type") for event in events]
    if not all(isinstance(event_type, str) for event_type in event_types):
        raise CompositeSummaryError(f"{record.get('run_id', '<unknown>')}: every event needs a string type")
    return event_types


def _all_failures_resolved_by_substitution(outcome: dict[str, Any]) -> bool:
    resolved_failure_ids = {
        repair.get("failure_id")
        for repair in outcome.get("repairs", [])
        if repair.get("action") == "substitute_and_resume"
        and repair.get("verified")
        and repair.get("completed", False)
    }
    failure_ids = {failure.get("failure_id") for failure in outcome.get("failures", [])}
    return bool(failure_ids) and None not in failure_ids and failure_ids <= resolved_failure_ids


def false_value_propagated(record: dict[str, Any]) -> bool:
    """Apply the WP1 false-value rule plus composite downstream evidence.

    WP1 flags rejected non-null values and unresolved failures that still produce
    output. Composite records store rejected semantic values in plan slots rather
    than ``tool_results``, so event and provenance evidence is also required:
    legacy numeric fallbacks that reach output are false; the Case 7 poison is
    false only when it reaches the terminal output without a successful M2
    replacement; and Case 9's known A2 semantic poison is false when it reaches
    the terminal output through the substitute source.
    """
    outcome = record["outcome"]
    tool_results = outcome["tool_results"]
    if any(
        result.get("status") == "rejected" and result.get("value") is not None
        for result in tool_results.values()
    ):
        return True
    if outcome.get("failures") and outcome.get("final_output") is not None:
        if not _all_failures_resolved_by_substitution(outcome):
            return True

    final_output = outcome.get("final_output")
    if final_output is None:
        return False
    event_types = _event_types(record)
    if "legacy_fallback" in event_types:
        return True

    labels = _source_labels(record)
    case_id = record["case_id"]
    if case_id == "case_7":
        poison_reached_terminal = any("poisoned_" in label for label in labels)
        corrected = SUBSTITUTED_EVENT in event_types and final_output == 25.0
        return poison_reached_terminal and not corrected
    if case_id == "case_9":
        terminal_labels = record["provenance"].get("C", [])
        return any(label == "substitute:RiskyQuoteSubstitute" for label in terminal_labels)
    return False


def load_group(path: Path, variant: str, case_id: str) -> list[dict[str, Any]]:
    if not path.is_file():
        raise CompositeSummaryError(f"missing input file: {path.relative_to(REPOSITORY_ROOT)}")
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise CompositeSummaryError(f"{path.name}:{line_number}: invalid JSON: {error}") from error
        records.append(record)

    if len(records) != EXPECTED_TRIALS:
        raise CompositeSummaryError(f"{path.name}: expected {EXPECTED_TRIALS} records, found {len(records)}")
    if {record.get("variant") for record in records} != {variant}:
        raise CompositeSummaryError(f"{path.name}: variant does not match {variant}")
    if {record.get("case_id") for record in records} != {case_id}:
        raise CompositeSummaryError(f"{path.name}: case_id does not match {case_id}")
    trials = sorted(record.get("trial") for record in records)
    if trials != list(range(1, EXPECTED_TRIALS + 1)):
        raise CompositeSummaryError(f"{path.name}: trials must be exactly 1..{EXPECTED_TRIALS}: {trials}")
    run_ids = [record.get("run_id") for record in records]
    if None in run_ids or len(set(run_ids)) != len(run_ids):
        raise CompositeSummaryError(f"{path.name}: run_id values must be present and unique")
    for record in records:
        _event_types(record)
        _source_labels(record)
        budget = record.get("budget")
        if not isinstance(budget, dict) or not all(key in budget for key in ("total", "consumed", "remaining")):
            raise CompositeSummaryError(f"{record['run_id']}: incomplete budget object")
        if budget["consumed"] + budget["remaining"] != budget["total"]:
            raise CompositeSummaryError(f"{record['run_id']}: inconsistent budget totals: {budget}")
    return records


def summarize(records: list[dict[str, Any]], source_path: Path) -> dict[str, Any]:
    statuses = Counter(record["outcome"]["status"] for record in records)
    completed = statuses["success"]
    retained = sum(record["outcome"]["status"] in {"success", "partial_success"} for record in records)
    false_values = sum(false_value_propagated(record) for record in records)
    event_types = [event_type for record in records for event_type in _event_types(record)]
    labels = [label for record in records for label in _source_labels(record)]
    consumed = sum(record["budget"]["consumed"] for record in records)
    exhausted = sum(record["budget"]["remaining"] == 0 for record in records)
    substitute_markers = sum(
        label.startswith("substitute:") and "poisoned_" not in label for label in labels
    )
    poisoned_markers = sum("poisoned_" in label for label in labels)
    trials = len(records)
    return {
        "schema_version": "1.0",
        "source_schema_version": records[0]["schema_version"],
        "source_file": str(source_path.relative_to(REPOSITORY_ROOT)),
        "variant": records[0]["variant"],
        "case_id": records[0]["case_id"],
        "git_commit": records[0]["git_commit"],
        "plan_digest": records[0]["plan_digest"],
        "trials": trials,
        "success": statuses["success"],
        "partial_success": statuses["partial_success"],
        "failed": statuses["failed"],
        "full_task_completion_count": completed,
        "full_task_completion_rate": completed / trials,
        "useful_result_retention_count": retained,
        "useful_result_retention_rate": retained / trials,
        "false_value_propagation_count": false_values,
        "false_value_propagation_rate": false_values / trials,
        "budget_consumed_total": consumed,
        "budget_exhaustion_count": exhausted,
        "explicit_degradation_count": event_types.count(DEGRADED_EVENT),
        "recovery_substitution_count": event_types.count(SUBSTITUTED_EVENT),
        "substitute_source_marker_count": substitute_markers,
        "poisoned_source_marker_count": poisoned_markers,
    }


def assert_acceptance(groups: dict[tuple[str, str], list[dict[str, Any]]]) -> None:
    case_eight = groups[("m2", "case_8")]
    case_eight_diagnostics: list[str] = []
    for record in case_eight:
        degraded_for_budget = any(
            event.get("type") == DEGRADED_EVENT and event.get("reason") == "recovery_budget_exhausted"
            for event in record["events"]
        )
        if false_value_propagated(record) or record["budget"]["remaining"] != 0 or not degraded_for_budget:
            case_eight_diagnostics.append(
                f"run_id={record['run_id']} trial={record['trial']} false_value={false_value_propagated(record)} "
                f"budget={record['budget']} degraded_for_budget={degraded_for_budget}"
            )
    if case_eight_diagnostics:
        raise CompositeSummaryError(
            "M2 Case 8 must exhaust its budget, degrade explicitly, and propagate no false value:\n  "
            + "\n  ".join(case_eight_diagnostics)
        )

    case_seven_diagnostics: list[str] = []
    for variant in VARIANT_ORDER:
        for record in groups[(variant, "case_7")]:
            poisoned_steps = {
                step_id
                for step_id, labels in record["provenance"].items()
                if any("poisoned_" in label for label in labels)
            }
            if not {"B", "C"} <= poisoned_steps:
                case_seven_diagnostics.append(
                    f"variant={variant} run_id={record['run_id']} trial={record['trial']} "
                    f"poisoned_steps={sorted(poisoned_steps)}"
                )
    if case_seven_diagnostics:
        raise CompositeSummaryError(
            "Case 7 semantic false values must carry poisoned provenance at B and downstream C:\n  "
            + "\n  ".join(case_seven_diagnostics)
        )


def _csv_row(summary: dict[str, Any]) -> dict[str, Any]:
    omitted = {"schema_version", "source_schema_version", "source_file", "git_commit", "plan_digest"}
    return {key: value for key, value in summary.items() if key not in omitted}


def write_group(summary: dict[str, Any]) -> None:
    name = f"{summary['variant']}-{summary['case_id'].replace('_', '')}"
    group_dir = OUTPUT_DIR / name
    group_dir.mkdir(parents=True, exist_ok=True)
    (group_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    row = _csv_row(summary)
    with (group_dir / "summary.csv").open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(row), lineterminator="\n")
        writer.writeheader()
        writer.writerow(row)

    rate = lambda key: f"{summary[key]:.1%}"
    lines = [
        f"# WP2 Composite {summary['variant'].upper()} {summary['case_id'].replace('_', ' ').title()}",
        "",
        f"- Source: `{summary['source_file']}`",
        f"- Git commit: `{summary['git_commit']}`",
        f"- Plan digest: `{summary['plan_digest']}`",
        f"- Trials: {summary['trials']}",
        "",
        "| Metric | Count | Rate |",
        "| --- | ---: | ---: |",
        f"| Full task completion | {summary['full_task_completion_count']} | {rate('full_task_completion_rate')} |",
        f"| Useful-result retention | {summary['useful_result_retention_count']} | {rate('useful_result_retention_rate')} |",
        f"| False-value propagation | {summary['false_value_propagation_count']} | {rate('false_value_propagation_rate')} |",
        "",
        "| Budget and source evidence | Count |",
        "| --- | ---: |",
        f"| Recovery budget consumed | {summary['budget_consumed_total']} |",
        f"| Budget exhausted runs | {summary['budget_exhaustion_count']} |",
        f"| Explicit degradation events | {summary['explicit_degradation_count']} |",
        f"| Recovery substitution events | {summary['recovery_substitution_count']} |",
        f"| Substitute source markers | {summary['substitute_source_marker_count']} |",
        f"| Poisoned source markers | {summary['poisoned_source_marker_count']} |",
        "",
        "Full completion counts only `success`. Useful-result retention counts `success` and",
        "`partial_success`, matching `analyze_replay.py`. Source-marker counts are occurrences",
        "across step provenance lists; substitute counts exclude poisoned markers.",
    ]
    (group_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_overview(summaries: list[dict[str, Any]]) -> None:
    lines = [
        "# WP2 Composite Experiment Overview",
        "",
        "Each row summarizes 30 deterministic runs.",
        "",
        "| Variant | Case | Completion | Retention | False value | Budget used | Exhausted | Degraded | Substituted | Substitute sources | Poisoned sources |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for summary in summaries:
        lines.append(
            f"| {summary['variant']} | {summary['case_id']} | "
            f"{summary['full_task_completion_rate']:.1%} | "
            f"{summary['useful_result_retention_rate']:.1%} | "
            f"{summary['false_value_propagation_rate']:.1%} | "
            f"{summary['budget_consumed_total']} | {summary['budget_exhaustion_count']} | "
            f"{summary['explicit_degradation_count']} | {summary['recovery_substitution_count']} | "
            f"{summary['substitute_source_marker_count']} | {summary['poisoned_source_marker_count']} |"
        )
    lines.extend(
        [
            "",
            "## WP1 single-point comparison framework",
            "",
            "| Comparison question | WP1 field | WP2 field | Interpretation |",
            "| --- | --- | --- | --- |",
            "| Did the whole plan finish? | `full_task_completion_rate` | `full_task_completion_rate` | Direct rate comparison is valid. |",
            "| Was a usable partial result retained? | `useful_result_retention_rate` | `useful_result_retention_rate` | Both count `success` and `partial_success`. |",
            "| Did an unverified value escape? | `false_value_rate` | `false_value_propagation_rate` | WP2 additionally checks downstream event and provenance evidence. |",
            "| Was recovery bounded? | Repair evidence | Budget consumed and exhausted counts | Compare policy behavior; WP1 summaries do not expose the same budget counters. |",
            "| Can substituted or poisoned inputs be traced? | Repair records | Source-marker counts | WP2 adds per-step provenance, so this is not a direct numeric comparison. |",
            "",
            "A final WP1 versus WP2 claim should compare matched variants and attack semantics.",
            "Cases 7–9 add dependencies, shared-budget exhaustion, and a join, so their raw rates",
            "should not be pooled with single-point cases without identifying the case mix.",
        ]
    )
    (OUTPUT_DIR / "composite-overview.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run() -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    source_paths: dict[tuple[str, str], Path] = {}
    for variant in VARIANT_ORDER:
        for case_id in CASE_ORDER:
            case_number = case_id.removeprefix("case_")
            source_path = RAW_DIR / f"{variant}-case{case_number}.jsonl"
            key = (variant, case_id)
            groups[key] = load_group(source_path, variant, case_id)
            source_paths[key] = source_path

    assert_acceptance(groups)
    summaries = [
        summarize(groups[(variant, case_id)], source_paths[(variant, case_id)])
        for variant in VARIANT_ORDER
        for case_id in CASE_ORDER
    ]
    for summary in summaries:
        write_group(summary)
    write_overview(summaries)
    return summaries


def main() -> int:
    try:
        summaries = run()
    except (CompositeSummaryError, KeyError, TypeError) as error:
        print(f"composite summary failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps([_csv_row(summary) for summary in summaries], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
