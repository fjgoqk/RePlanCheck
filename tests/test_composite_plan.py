import pytest
from pydantic import BaseModel

from src.ace.plan.composite import (
    BOTTOM,
    BudgetAllocator,
    BudgetExhausted,
    CompositePlan,
    CompositeRecovery,
    DependencyGraph,
    PlanStep,
    Provenance,
    RecoveryDegradedEvent,
    RecoverySubstitutedEvent,
    from_abstract_plan,
)
from src.ace.recovery import RepairPolicy
from src.ace.schema.abstract import AbstractPlan, AbstractTool
from src.ace.schema.concrete import ConcreteToolBase
from src.ace.schema.permissions import Permission
from src.ace.schema.recovery import FailureKind, RepairAction


class EmptyInput(BaseModel):
    pass


class ValueOutput(BaseModel):
    value: str


def make_tool(name: str) -> AbstractTool:
    return AbstractTool(
        name=name,
        description=f"Run {name}",
        args_schema=EmptyInput,
        output_schema=ValueOutput,
    )


def make_step(step_id: str) -> PlanStep:
    return PlanStep(id=step_id, tool=make_tool(step_id))


def test_topological_sort_fan_queries_and_reachability():
    graph = DependencyGraph()
    for step_id in ("fetch", "parse", "store"):
        graph.add_step(make_step(step_id))
    graph.add_edge("fetch", "parse")
    graph.add_edge("parse", "store")

    assert graph.topological_sort() == ["fetch", "parse", "store"]
    assert graph.fan_in("parse") == {"fetch"}
    assert graph.fan_out("parse") == {"store"}
    assert graph.is_reachable("fetch", "store")
    assert not graph.is_reachable("store", "fetch")


def test_topological_sort_rejects_a_cycle():
    graph = DependencyGraph()
    graph.add_step(make_step("first"))
    graph.add_step(make_step("second"))
    graph.add_edge("first", "second")
    graph.add_edge("second", "first")

    assert graph.has_cycle()
    with pytest.raises(ValueError, match="contains a cycle"):
        graph.topological_sort()


def test_provenance_propagates_along_dependencies():
    graph = DependencyGraph()
    graph.add_step(make_step("source"))
    graph.add_step(make_step("consumer"))
    graph.add_edge("source", "consumer")
    provenance = Provenance()
    provenance.set_sources("source", "value", {"external", "substitute:mirror"})

    provenance.propagate(graph)

    assert provenance.sources_for("consumer") == {
        "external",
        "substitute:mirror",
        "step:source",
        "step:consumer",
    }


def test_single_step_abstract_plan_has_no_dependency_edges():
    tool = make_tool("Lookup")
    abstract_plan = AbstractPlan(
        script='def main():\n    result = Lookup(query="example")\n    return result',
        abs_tools=[tool],
    )

    composite = from_abstract_plan(abstract_plan)

    assert isinstance(composite, CompositePlan)
    assert len(composite.graph.steps) == 1
    assert composite.graph.edges == set()
    assert composite.graph.steps["step_1"].tool is tool
    assert composite.provenance.sources_for("step_1", "value") == {"external", "step:step_1"}


def test_conversion_builds_data_dependency_from_tool_output():
    fetch = make_tool("Fetch")
    summarize = make_tool("Summarize")
    abstract_plan = AbstractPlan(
        script=(
            "def main():\n"
            '    fetched = Fetch(query="example")\n'
            "    summary = Summarize(text=fetched.value)\n"
            "    return summary"
        ),
        abs_tools=[fetch, summarize],
    )

    composite = CompositePlan.from_abstract_plan(abstract_plan)

    assert composite.graph.edges == {("step_1", "step_2")}
    assert composite.graph.steps["step_2"].inputs["text"].step_id == "step_1"
    assert composite.graph.steps["step_2"].inputs["text"].output == "value"
    assert composite.provenance.sources_for("step_2", "value") == {
        "external",
        "step:step_1",
        "step:step_2",
    }


def test_plan_step_exposes_default_and_custom_recovery_budget():
    assert make_step("default").budget == 1
    assert PlanStep(id="custom", tool=make_tool("custom"), budget=3).budget == 3


def make_composite(*steps: PlanStep, total_budget: int | None = None) -> CompositePlan:
    graph = DependencyGraph()
    for step in steps:
        graph.add_step(step)
    return CompositePlan(graph=graph, total_budget=total_budget)


def test_budget_allocator_uses_step_budgets_and_returns_step_remaining():
    first = PlanStep(id="first", tool=make_tool("first"), budget=2)
    second = PlanStep(id="second", tool=make_tool("second"), budget=1)
    plan = make_composite(first, second)

    assert plan.total_budget == 3
    assert plan.consume_for(first) == 1
    assert plan.budget_allocator.consume(second) == 0
    assert plan.budget_allocator.consumed == 2
    assert plan.budget_allocator.remaining == 1


def test_total_budget_caps_recovery_across_steps():
    plan = make_composite(make_step("first"), make_step("second"), total_budget=1)

    assert plan.consume_for("first") == 0
    assert not plan.can_recover("second")
    with pytest.raises(BudgetExhausted, match="second"):
        plan.consume_for("second")
    assert plan.budget_allocator.consumed == plan.total_budget == 1


def test_steps_cannot_borrow_another_steps_unused_budget():
    first = make_step("first")
    second = PlanStep(id="second", tool=make_tool("second"), budget=3)
    plan = make_composite(first, second, total_budget=4)

    assert plan.consume_for("first") == 0
    with pytest.raises(BudgetExhausted, match="first"):
        plan.consume_for("first")

    assert plan.budget_allocator.consumed == 1
    assert plan.budget_allocator.remaining_for("second") == 3
    assert plan.total_budget is not None
    assert plan.budget_allocator.consumed <= plan.total_budget


def test_exhausted_step_can_only_be_degraded():
    plan = make_composite(make_step("only"))

    assert plan.can_recover("only")
    assert plan.consume_for("only") == 0
    assert not plan.can_recover("only")
    with pytest.raises(BudgetExhausted, match="only"):
        plan.consume_for("only")

    event = plan.degrade("only")
    assert event == RecoveryDegradedEvent(step_id="only")
    assert plan.recovery_events == (event,)


def test_degrade_permanently_disables_recovery_with_budget_remaining():
    step = PlanStep(id="optional", tool=make_tool("optional"), budget=2)
    plan = make_composite(step)

    plan.degrade(step)

    assert not plan.can_recover(step)
    assert plan.budget_allocator.remaining_for(step) == 2
    with pytest.raises(BudgetExhausted, match="optional"):
        plan.consume_for(step)


def test_single_step_total_one_cannot_substitute_again_after_consumption():
    plan = make_composite(make_step("single"), total_budget=1)

    assert plan.consume_for("single") == 0
    with pytest.raises(BudgetExhausted, match="single"):
        plan.consume_for("single")
    assert plan.budget_allocator.consumed == 1


def test_budget_allocator_rejects_negative_total_and_unknown_steps():
    plan = make_composite(make_step("known"))

    with pytest.raises(ValueError, match="non-negative"):
        BudgetAllocator(plan, total_budget=-1)
    with pytest.raises(KeyError, match="missing"):
        plan.can_recover("missing")


class RecoveryTool(ConcreteToolBase):
    def generate_source(self) -> str:
        return "def main():\n    return {'value': 'recovered'}\n"


def make_recovery_tool(
    name: str,
    *,
    clearances: set[str] | None = None,
    permissions: set[Permission] | None = None,
) -> RecoveryTool:
    return RecoveryTool(
        name=name,
        provider="test",
        description="recovery fixture",
        clearances=clearances or {"public"},
        permissions=permissions or set(),
        args_schema=EmptyInput,
        output_schema=ValueOutput,
    )


def make_recovery_context(
    *,
    budget: int = 1,
    total_budget: int | None = None,
    substitutes: tuple[RecoveryTool, ...] | None = None,
):
    abstract_tool = make_tool("Lookup")
    step = PlanStep(id="lookup", tool=abstract_tool, budget=budget)
    composite = make_composite(step, total_budget=total_budget)
    abstract_plan = AbstractPlan(
        script="def main():\n    return Lookup()",
        abs_tools=[abstract_tool],
    )
    selected = make_recovery_tool("LookupPrimary")
    replacement = make_recovery_tool("LookupMirror")
    recovery = CompositeRecovery(
        plan=composite,
        abstract_plan=abstract_plan,
        selected_tools={"Lookup": selected},
        approved_substitutions={"Lookup": substitutes if substitutes is not None else (replacement,)},
        invoke=lambda tool, inputs: {"value": f"{tool.name}:{len(inputs)}"},
    )
    return composite, step, abstract_plan, selected, replacement, recovery


def test_composite_recovery_substitutes_and_consumes_budget():
    plan, step, _, _, _, recovery = make_recovery_context()

    result = recovery.recover(step, {"value": 7}, {})

    assert result == {"value": "LookupMirror:0"}
    assert plan.output_for(step, "value") == "LookupMirror:0"
    assert plan.budget_allocator.consumed == 1


def test_composite_recovery_budget_exhaustion_degrades_to_bottom():
    plan, step, _, _, _, recovery = make_recovery_context(budget=1)
    recovery.recover(step, {"value": 7}, {})

    result = recovery.recover(step, {"value": 8}, {})

    assert result is BOTTOM
    assert plan.output_for(step, "value") is BOTTOM
    assert recovery.events[-1] == RecoveryDegradedEvent(step_id="lookup", reason="recovery_budget_exhausted")


def test_composite_recovery_without_substitute_degrades_without_forging_value():
    plan, step, _, _, _, recovery = make_recovery_context(substitutes=())

    result = recovery.recover(step, {"value": "untrusted"}, {})

    assert result is BOTTOM
    assert plan.output_for(step, "value") is BOTTOM
    assert plan.budget_allocator.consumed == 0
    assert plan.recovery_events[-1].reason == "no_approved_substitute"


def test_composite_recovery_writes_substitute_provenance_label():
    plan, step, _, _, replacement, recovery = make_recovery_context()

    recovery.recover(step, {"value": "bad"}, {})

    assert Provenance.substitute_label(replacement) in plan.provenance.sources_for(step.id, "value")


def test_composite_recovery_records_verified_substitution_event():
    _, step, _, _, replacement, recovery = make_recovery_context()

    recovery.recover(step, {"value": "bad"}, {}, affected_fields=("value",))

    event = recovery.events[-1]
    assert isinstance(event, RecoverySubstitutedEvent)
    assert event.replacement_tool == replacement.name
    assert event.failure.affected_fields == ("value",)
    assert event.patch.verified
    assert event.patch.action is RepairAction.SUBSTITUTE_AND_RESUME


def test_single_step_composite_recovery_matches_wp1_substitution_semantics():
    _, step, abstract_plan, selected, replacement, recovery = make_recovery_context()
    policy = RepairPolicy()
    _, wp1_patch = policy.propose_substitution(
        plan=abstract_plan,
        tools={"Lookup": selected},
        abstract_tool="Lookup",
        concrete_tool=selected,
        replacement_tool=replacement,
        approved_tools=(selected.name, replacement.name),
        approved_permissions=(),
        output={"value": "bad"},
        affected_fields=("value",),
    )

    result = recovery.recover(
        step,
        {"value": "bad"},
        {},
        affected_fields=("value",),
    )
    composite_event = recovery.events[-1]

    assert result == {"value": "LookupMirror:0"}
    assert isinstance(composite_event, RecoverySubstitutedEvent)
    assert composite_event.patch.action is wp1_patch.action
    assert composite_event.patch.replacement_tool == wp1_patch.replacement_tool
    assert composite_event.patch.tools_before == wp1_patch.tools_before
    assert composite_event.patch.permissions_before == wp1_patch.permissions_before


def test_composite_recovery_total_consumption_never_exceeds_total_budget():
    first = PlanStep(id="first", tool=make_tool("First"), budget=2)
    second = PlanStep(id="second", tool=make_tool("Second"), budget=2)
    plan = make_composite(first, second, total_budget=1)
    abstract_plan = AbstractPlan(
        script="def main():\n    First()\n    return Second()",
        abs_tools=[first.tool, second.tool],
    )
    selected = {
        "First": make_recovery_tool("FirstPrimary"),
        "Second": make_recovery_tool("SecondPrimary"),
    }
    recovery = CompositeRecovery(
        plan,
        abstract_plan,
        selected,
        {
            "First": (make_recovery_tool("FirstMirror"),),
            "Second": (make_recovery_tool("SecondMirror"),),
        },
        lambda tool, inputs: {"value": tool.name},
    )

    recovery.recover(first, {"value": "bad"}, {})
    recovery.recover(second, {"value": "bad"}, {})

    assert plan.budget_allocator.consumed == plan.total_budget == 1
    assert plan.output_for(second, "value") is BOTTOM


def test_composite_recovery_rejects_non_h1_failure():
    plan, step, _, _, _, recovery = make_recovery_context()

    result = recovery.recover(step, {"value": "bad"}, {}, failure_kind="H2")

    assert result is BOTTOM
    assert plan.budget_allocator.consumed == 0
    assert recovery.events[-1] == RecoveryDegradedEvent(step_id="lookup", reason="failure_not_h1")


def test_composite_recovery_rejects_permission_increase_before_invocation():
    unsafe = make_recovery_tool("UnsafeMirror", permissions={Permission.NETWORK})
    plan, step, _, _, _, recovery = make_recovery_context(substitutes=(unsafe,))

    result = recovery.recover(
        step,
        {"value": "bad"},
        {},
        failure_kind=FailureKind.OUTPUT_SCHEMA_VALIDATION,
    )

    assert result is BOTTOM
    assert plan.budget_allocator.consumed == 0
    assert plan.recovery_events[-1].reason == "no_approved_substitute"
