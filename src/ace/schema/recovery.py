from dataclasses import dataclass
from enum import StrEnum


class FailureKind(StrEnum):
    OUTPUT_SCHEMA_VALIDATION = "output_schema_validation"


class RepairAction(StrEnum):
    REJECT_OUTPUT_AND_RESUME = "reject_output_and_resume"


@dataclass(frozen=True)
class ToolFailure:
    failure_id: str
    kind: FailureKind
    abstract_tool: str
    concrete_tool: str
    output_digest: str
    affected_fields: tuple[str, ...]
    attempt: int


@dataclass(frozen=True)
class RepairPatch:
    patch_id: str
    failure_id: str
    action: RepairAction
    abstract_tool: str
    concrete_tool: str
    plan_digest_before: str
    plan_digest_after: str
    tools_before: tuple[str, ...]
    tools_after: tuple[str, ...]
    permissions_before: tuple[str, ...]
    permissions_after: tuple[str, ...]
    attempt: int
    verified: bool = False
