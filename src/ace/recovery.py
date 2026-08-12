import hashlib
import json
from collections import defaultdict
from dataclasses import replace

from .schema.abstract import AbstractPlan
from .schema.concrete import ConcreteToolBase
from .schema.recovery import FailureKind, RepairAction, RepairPatch, ToolFailure


class RepairRejectedError(RuntimeError):
    pass


def _digest_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _tool_names(tools: dict[str, ConcreteToolBase]) -> tuple[str, ...]:
    return tuple(sorted(tools))


def _permissions(tools: dict[str, ConcreteToolBase]) -> tuple[str, ...]:
    return tuple(
        sorted(
            f"{abstract_name}:{permission.value}"
            for abstract_name, tool in tools.items()
            for permission in tool.permissions
        )
    )


def build_output_validation_failure(
    plan: AbstractPlan,
    tools: dict[str, ConcreteToolBase],
    abstract_tool: str,
    concrete_tool: ConcreteToolBase,
    output: object,
    affected_fields: tuple[str, ...],
    attempt: int,
) -> ToolFailure:
    """Create a safe failure record without retaining untrusted output."""

    if abstract_tool not in tools or tools[abstract_tool].name != concrete_tool.name:
        raise RepairRejectedError("Failed tool is not part of the approved concrete plan")

    plan_digest = _digest_text(plan.script)
    output_json = json.dumps(output, sort_keys=True, default=str, separators=(",", ":"))
    output_digest = _digest_text(output_json)
    failure_id = _digest_text(f"{plan_digest}:{abstract_tool}:{attempt}:{output_digest}")[:16]
    return ToolFailure(
        failure_id=failure_id,
        kind=FailureKind.OUTPUT_SCHEMA_VALIDATION,
        abstract_tool=abstract_tool,
        concrete_tool=concrete_tool.name,
        output_digest=output_digest,
        affected_fields=affected_fields,
        attempt=attempt,
    )


class RepairPolicy:
    """Builds and verifies bounded local recovery patches without an LLM."""

    def __init__(self, max_repairs_per_tool: int = 1):
        if max_repairs_per_tool < 1:
            raise ValueError("max_repairs_per_tool must be at least 1")
        self.max_repairs_per_tool = max_repairs_per_tool
        self._attempts: defaultdict[str, int] = defaultdict(int)

    def propose_output_rejection(
        self,
        plan: AbstractPlan,
        tools: dict[str, ConcreteToolBase],
        abstract_tool: str,
        concrete_tool: ConcreteToolBase,
        output: object,
        affected_fields: tuple[str, ...],
    ) -> tuple[ToolFailure, RepairPatch]:
        attempt = self._attempts[abstract_tool] + 1
        if attempt > self.max_repairs_per_tool:
            raise RepairRejectedError(f"Repair budget exhausted for {abstract_tool}")

        plan_digest = _digest_text(plan.script)
        failure = build_output_validation_failure(
            plan=plan,
            tools=tools,
            abstract_tool=abstract_tool,
            concrete_tool=concrete_tool,
            output=output,
            affected_fields=affected_fields,
            attempt=attempt,
        )
        tool_names = _tool_names(tools)
        permissions = _permissions(tools)

        candidate = RepairPatch(
            patch_id=_digest_text(f"repair:{failure.failure_id}")[:16],
            failure_id=failure.failure_id,
            action=RepairAction.REJECT_OUTPUT_AND_RESUME,
            abstract_tool=abstract_tool,
            concrete_tool=concrete_tool.name,
            plan_digest_before=plan_digest,
            plan_digest_after=plan_digest,
            tools_before=tool_names,
            tools_after=tool_names,
            permissions_before=permissions,
            permissions_after=permissions,
            attempt=attempt,
        )
        self.verify(candidate)
        self._attempts[abstract_tool] = attempt
        return failure, replace(candidate, verified=True)

    def propose_substitution(
        self,
        plan: AbstractPlan,
        tools: dict[str, ConcreteToolBase],
        abstract_tool: str,
        concrete_tool: ConcreteToolBase,
        replacement_tool: ConcreteToolBase,
        approved_tools: tuple[str, ...],
        approved_permissions: tuple[str, ...],
        output: object,
        affected_fields: tuple[str, ...],
    ) -> tuple[ToolFailure, RepairPatch]:
        attempt = self._attempts[abstract_tool] + 1
        if attempt > self.max_repairs_per_tool:
            raise RepairRejectedError(f"Repair budget exhausted for {abstract_tool}")
        if concrete_tool.name not in approved_tools or replacement_tool.name not in approved_tools:
            raise RepairRejectedError("Substitution uses a tool outside the pre-approved recovery set")
        if concrete_tool.name == replacement_tool.name:
            raise RepairRejectedError("Substitution must select a different concrete tool")

        plan_digest = _digest_text(plan.script)
        failure = build_output_validation_failure(
            plan=plan,
            tools=tools,
            abstract_tool=abstract_tool,
            concrete_tool=concrete_tool,
            output=output,
            affected_fields=affected_fields,
            attempt=attempt,
        )
        candidate = RepairPatch(
            patch_id=_digest_text(f"substitute:{failure.failure_id}:{replacement_tool.name}")[:16],
            failure_id=failure.failure_id,
            action=RepairAction.SUBSTITUTE_AND_RESUME,
            abstract_tool=abstract_tool,
            concrete_tool=concrete_tool.name,
            replacement_tool=replacement_tool.name,
            plan_digest_before=plan_digest,
            plan_digest_after=plan_digest,
            tools_before=approved_tools,
            tools_after=approved_tools,
            permissions_before=approved_permissions,
            permissions_after=approved_permissions,
            attempt=attempt,
            completed=False,
        )
        self.verify(candidate)
        self._attempts[abstract_tool] = attempt
        return failure, replace(candidate, verified=True)

    def verify(self, patch: RepairPatch) -> None:
        if patch.action not in {RepairAction.REJECT_OUTPUT_AND_RESUME, RepairAction.SUBSTITUTE_AND_RESUME}:
            raise RepairRejectedError("Unsupported repair action")
        if patch.plan_digest_before != patch.plan_digest_after:
            raise RepairRejectedError("Repair changes the trusted plan")
        if patch.tools_before != patch.tools_after:
            raise RepairRejectedError("Repair changes the approved tool set")
        if patch.permissions_before != patch.permissions_after:
            raise RepairRejectedError("Repair changes the approved permissions")
        if patch.attempt > self.max_repairs_per_tool:
            raise RepairRejectedError("Repair exceeds the per-tool budget")
        if patch.action is RepairAction.SUBSTITUTE_AND_RESUME:
            if not patch.replacement_tool:
                raise RepairRejectedError("Substitution is missing a replacement tool")
            if patch.concrete_tool not in patch.tools_before or patch.replacement_tool not in patch.tools_before:
                raise RepairRejectedError("Substitution tool is outside the approved tool set")
