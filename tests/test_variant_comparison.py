import json

import pytest

from experiments.analysis.compare_variants import STAGE05_VARIANTS, compare, load_summaries


def _summary(
    variant: str,
    useful: float,
    false_value: float,
    repair: float | None,
    full_completion: float = 0.0,
) -> dict:
    def case(case_id: str, attacked: bool) -> dict:
        return {
            "case_id": case_id,
            "trials": 30,
            "success": round(30 * full_completion) if attacked else 30,
            "partial_success": round(30 * useful) if attacked and not full_completion else 0,
            "failed": 30 if attacked and not useful else 0,
            "full_task_completion_rate": full_completion if attacked else 1.0,
            "useful_result_retention_rate": useful if attacked else 1.0,
            "tool_mapping_match_rate": 1.0,
            "attack_block_rate": 1.0 if attacked else None,
            "false_value_rate": false_value if attacked else None,
            "repair_success_rate": repair if attacked else None,
            "invariant_pass_rate": repair if attacked else None,
            "mean_latency_ms": 3000.0,
            "p95_latency_ms": 3200,
            "min_latency_ms": 2800,
            "max_latency_ms": 3400,
        }

    return {
        "variant": variant,
        "git_commit": "commit",
        "plan_digest": "plan",
        "total_trials": 90,
        "cases": [case("case_1", False), case("case_2", True), case("case_3", True)],
    }


def test_comparison_aggregates_attack_cases_only():
    rows = compare(
        [
            _summary("baseline", 0.0, 0.0, 0.0),
            _summary("m0", 1.0, 1.0, 1.0),
            _summary("m1", 1.0, 0.0, 1.0),
        ]
    )

    assert rows[0]["attack_trials"] == 60
    assert rows[0]["attack_full_completion_rate"] == 0.0
    assert rows[0]["useful_result_retention_rate"] == 0.0
    assert rows[1]["false_value_rate"] == 1.0
    assert rows[2]["false_value_rate"] == 0.0
    assert all(row["normal_success_rate"] == 1.0 for row in rows)


def test_stage05_loader_accepts_m2_and_reports_full_recovery(tmp_path):
    summaries = [
        _summary("baseline", 0.0, 0.0, 0.0),
        _summary("m0", 1.0, 1.0, 1.0),
        _summary("m1", 1.0, 0.0, 1.0),
        _summary("m2", 1.0, 0.0, 1.0, full_completion=1.0),
    ]
    paths = []
    for summary in summaries:
        path = tmp_path / f"{summary['variant']}.json"
        path.write_text(json.dumps(summary), encoding="utf-8")
        paths.append(path)

    loaded = load_summaries(paths, expected_variants=STAGE05_VARIANTS)
    rows = compare(loaded)

    assert [row["variant"] for row in rows] == ["baseline", "m0", "m1", "m2"]
    assert rows[-1]["attack_full_completion_rate"] == 1.0


def test_loader_rejects_mixed_commits(tmp_path):
    summaries = [
        _summary("baseline", 0.0, 0.0, 0.0),
        _summary("m0", 1.0, 1.0, 1.0),
        _summary("m1", 1.0, 0.0, 1.0),
    ]
    summaries[2]["git_commit"] = "different"
    paths = []
    for summary in summaries:
        path = tmp_path / f"{summary['variant']}.json"
        path.write_text(json.dumps(summary), encoding="utf-8")
        paths.append(path)

    with pytest.raises(ValueError, match="different Git commits"):
        load_summaries(paths)
