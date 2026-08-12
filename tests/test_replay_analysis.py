import json

import pytest

from experiments.analysis.analyze_replay import load_and_validate, summarize


def _record(run_id: str, case_id: str, trial: int, status: str, attacked: bool) -> dict:
    failures = [{"kind": "output_schema_validation"}] if attacked else []
    repairs = (
        [
            {
                "verified": True,
                "plan_digest_before": "plan",
                "plan_digest_after": "plan",
                "tools_before": ["a", "b"],
                "tools_after": ["a", "b"],
                "permissions_before": [],
                "permissions_after": [],
            }
        ]
        if attacked
        else []
    )
    return {
        "run_id": run_id,
        "schema_version": "1.1",
        "variant": "m1",
        "git_commit": "commit",
        "plan_digest": "plan",
        "case_id": case_id,
        "trial": trial,
        "duration_ms": 100 + trial,
        "expected_tools": ["QuickRide", "MetroHail"],
        "outcome": {
            "status": status,
            "final_output": None if attacked else 49.2,
            "tool_results": {
                "QuickRide": {"status": "rejected" if attacked else "success", "value": None if attacked else 49.2},
                "MetroHail": {"status": "success", "value": 33.0},
            },
            "failures": failures,
            "repairs": repairs,
        },
    }


def test_replay_summary_distinguishes_attack_metrics(tmp_path):
    records = [
        _record("run-1", "case_1", 1, "success", False),
        _record("run-2", "case_2", 1, "partial_success", True),
    ]
    path = tmp_path / "runs.jsonl"
    path.write_text("\n".join(json.dumps(record) for record in records))

    summaries = {row["case_id"]: row for row in summarize(load_and_validate(path))}

    assert summaries["case_1"]["attack_block_rate"] is None
    assert summaries["case_1"]["full_task_completion_rate"] == 1.0
    assert summaries["case_2"]["full_task_completion_rate"] == 0.0
    assert summaries["case_2"]["useful_result_retention_rate"] == 1.0
    assert summaries["case_2"]["attack_block_rate"] == 1.0
    assert summaries["case_2"]["false_value_rate"] == 0.0
    assert summaries["case_2"]["repair_success_rate"] == 1.0
    assert summaries["case_2"]["invariant_pass_rate"] == 1.0


def test_replay_validation_rejects_plan_drift(tmp_path):
    first = _record("run-1", "case_1", 1, "success", False)
    second = _record("run-2", "case_2", 1, "partial_success", True)
    second["plan_digest"] = "changed"
    path = tmp_path / "runs.jsonl"
    path.write_text("\n".join(json.dumps(record) for record in [first, second]))

    with pytest.raises(ValueError, match="Plan digest drift"):
        load_and_validate(path)
