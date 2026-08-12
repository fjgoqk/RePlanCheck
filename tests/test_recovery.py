from dataclasses import replace

import pytest

from src.ace.recovery import RepairPolicy, RepairRejectedError
from src.ace.schema.abstract import AbstractPlan
from src.ace.schema.permissions import Permission
from src.ace.schema.recovery import RepairAction


class StubTool:
    def __init__(self, name: str, permissions: set[Permission]):
        self.name = name
        self.permissions = permissions


def make_context():
    plan = AbstractPlan(script="def main():\n    return FareTool()", abs_tools=[])
    tool = StubTool("QuickRide", {Permission.NETWORK})
    tools = {"FareTool": tool}
    return plan, tool, tools


def test_output_rejection_patch_preserves_security_invariants():
    plan, tool, tools = make_context()
    policy = RepairPolicy(max_repairs_per_tool=1)

    failure, patch = policy.propose_output_rejection(
        plan=plan,
        tools=tools,
        abstract_tool="FareTool",
        concrete_tool=tool,
        output={"fare": "malicious instruction"},
        affected_fields=("fare",),
    )

    assert failure.output_digest
    assert "malicious instruction" not in repr(failure)
    assert patch.action is RepairAction.REJECT_OUTPUT_AND_RESUME
    assert patch.plan_digest_before == patch.plan_digest_after
    assert patch.tools_before == patch.tools_after
    assert patch.permissions_before == patch.permissions_after
    assert patch.verified is True


def test_repair_verifier_rejects_tool_set_change():
    plan, tool, tools = make_context()
    policy = RepairPolicy()
    _, patch = policy.propose_output_rejection(plan, tools, "FareTool", tool, {"fare": "bad"}, ("fare",))

    with pytest.raises(RepairRejectedError, match="tool set"):
        policy.verify(replace(patch, tools_after=("FareTool", "NewTool")))


def test_repair_budget_is_bounded_per_tool():
    plan, tool, tools = make_context()
    policy = RepairPolicy(max_repairs_per_tool=1)
    policy.propose_output_rejection(plan, tools, "FareTool", tool, {"fare": "bad"}, ("fare",))

    with pytest.raises(RepairRejectedError, match="budget exhausted"):
        policy.propose_output_rejection(plan, tools, "FareTool", tool, {"fare": "bad again"}, ("fare",))


def test_substitution_patch_uses_only_preapproved_tools():
    plan, tool, tools = make_context()
    replacement = StubTool("QuickRideVerified", {Permission.NETWORK})
    policy = RepairPolicy(max_repairs_per_tool=1)

    failure, patch = policy.propose_substitution(
        plan=plan,
        tools=tools,
        abstract_tool="FareTool",
        concrete_tool=tool,
        replacement_tool=replacement,
        approved_tools=("QuickRide", "QuickRideVerified"),
        approved_permissions=("QuickRide:network", "QuickRideVerified:network"),
        output={"fare": "bad"},
        affected_fields=("fare",),
    )

    assert patch.failure_id == failure.failure_id
    assert patch.action is RepairAction.SUBSTITUTE_AND_RESUME
    assert patch.replacement_tool == "QuickRideVerified"
    assert patch.verified is True
    assert patch.completed is False


def test_substitution_rejects_unapproved_replacement():
    plan, tool, tools = make_context()
    replacement = StubTool("UnknownTool", {Permission.NETWORK})
    policy = RepairPolicy()

    with pytest.raises(RepairRejectedError, match="pre-approved"):
        policy.propose_substitution(
            plan=plan,
            tools=tools,
            abstract_tool="FareTool",
            concrete_tool=tool,
            replacement_tool=replacement,
            approved_tools=("QuickRide",),
            approved_permissions=("QuickRide:network",),
            output={"fare": "bad"},
            affected_fields=("fare",),
        )
