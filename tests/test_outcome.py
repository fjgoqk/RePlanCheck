import json

from src.ace.experiment_log import JsonlExperimentWriter
from src.ace.schema.outcome import ExecutionOutcome, ExecutionStatus, ToolExecutionResult, ToolResultStatus
from src.ace.schema.recovery import FailureKind, RepairAction, RepairPatch, ToolFailure


def _failure() -> ToolFailure:
    return ToolFailure(
        failure_id="failure-1",
        kind=FailureKind.OUTPUT_SCHEMA_VALIDATION,
        abstract_tool="QuickRideFareEstimate",
        concrete_tool="QuickRide",
        output_digest="sha256:test",
        affected_fields=("fare",),
        attempt=1,
    )


def _repair() -> RepairPatch:
    return RepairPatch(
        patch_id="patch-1",
        failure_id="failure-1",
        action=RepairAction.REJECT_OUTPUT_AND_RESUME,
        abstract_tool="QuickRideFareEstimate",
        concrete_tool="QuickRide",
        plan_digest_before="plan",
        plan_digest_after="plan",
        tools_before=("QuickRide", "MetroHail"),
        tools_after=("QuickRide", "MetroHail"),
        permissions_before=("network",),
        permissions_after=("network",),
        attempt=1,
        verified=True,
    )


def test_partial_success_suppresses_generated_plan_fallback():
    outcome = ExecutionOutcome.from_execution(
        raw_final_output=0.0,
        tool_results={
            "QuickRide": ToolExecutionResult(status=ToolResultStatus.REJECTED, value=None),
            "MetroHail": ToolExecutionResult(status=ToolResultStatus.SUCCESS, value={"fare": 33.0}),
        },
        failures=[_failure()],
        repairs=[_repair()],
    )

    assert outcome.status is ExecutionStatus.PARTIAL_SUCCESS
    assert outcome.final_output is None
    assert outcome.tool_results["QuickRide"].value is None
    assert outcome.tool_results["MetroHail"].value == {"fare": 33.0}


def test_success_preserves_final_output():
    outcome = ExecutionOutcome.from_execution(
        raw_final_output=49.2,
        tool_results={
            "QuickRide": ToolExecutionResult(status=ToolResultStatus.SUCCESS, value={"fare": 49.2}),
        },
        failures=[],
        repairs=[],
    )

    assert outcome.status is ExecutionStatus.SUCCESS
    assert outcome.final_output == 49.2


def test_jsonl_writer_appends_machine_readable_record(tmp_path):
    outcome = ExecutionOutcome.from_execution(
        raw_final_output=0.0,
        tool_results={"QuickRide": ToolExecutionResult(status=ToolResultStatus.REJECTED, value=None)},
        failures=[_failure()],
        repairs=[_repair()],
    )
    output_path = tmp_path / "runs.jsonl"

    JsonlExperimentWriter(output_path).append(
        query="compare fares",
        llm_model="deepseek-v4-flash",
        embedding_model="BAAI/bge-small-en-v1.5",
        tool_manifest="manifest.json",
        temperature=0.0,
        duration_ms=123,
        outcome=outcome,
    )

    record = json.loads(output_path.read_text())
    assert record["schema_version"] == "1.1"
    assert record["outcome"]["status"] == "failed"
    assert record["outcome"]["final_output"] is None
    assert record["outcome"]["tool_results"]["QuickRide"] == {"status": "rejected", "value": None}
