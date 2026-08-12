from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict

from .recovery import RepairPatch, ToolFailure


class ExecutionStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"


class ExecutionVariant(StrEnum):
    """Execution semantics used by the deterministic replay experiment."""

    BASELINE = "baseline"
    M0 = "m0"
    M1 = "m1"


class ToolResultStatus(StrEnum):
    SUCCESS = "success"
    REJECTED = "rejected"
    FAILED = "failed"


class ToolExecutionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: ToolResultStatus
    value: Any | None = None


class ExecutionOutcome(BaseModel):
    """Trusted execution result assembled outside the generated plan."""

    model_config = ConfigDict(frozen=True)

    status: ExecutionStatus
    final_output: Any | None
    tool_results: dict[str, ToolExecutionResult]
    failures: list[ToolFailure]
    repairs: list[RepairPatch]

    @classmethod
    def from_execution(
        cls,
        raw_final_output: Any,
        tool_results: dict[str, ToolExecutionResult],
        failures: list[ToolFailure],
        repairs: list[RepairPatch],
    ) -> "ExecutionOutcome":
        has_success = any(result.status is ToolResultStatus.SUCCESS for result in tool_results.values())

        if failures:
            status = ExecutionStatus.PARTIAL_SUCCESS if has_success else ExecutionStatus.FAILED
            final_output = None
        else:
            status = ExecutionStatus.SUCCESS
            final_output = raw_final_output

        return cls(
            status=status,
            final_output=final_output,
            tool_results=dict(tool_results),
            failures=list(failures),
            repairs=list(repairs),
        )

    @classmethod
    def from_legacy_recovery(
        cls,
        raw_final_output: Any,
        tool_results: dict[str, ToolExecutionResult],
        failures: list[ToolFailure],
        repairs: list[RepairPatch],
    ) -> "ExecutionOutcome":
        """Represent M0, which exposes the generated plan's fallback value."""

        trusted_outcome = cls.from_execution(
            raw_final_output=raw_final_output,
            tool_results=tool_results,
            failures=failures,
            repairs=repairs,
        )
        if not failures:
            return trusted_outcome

        return cls(
            status=trusted_outcome.status,
            final_output=raw_final_output,
            tool_results=trusted_outcome.tool_results,
            failures=trusted_outcome.failures,
            repairs=trusted_outcome.repairs,
        )
