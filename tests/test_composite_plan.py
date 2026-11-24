import pytest
from pydantic import BaseModel

from src.ace.plan.composite import (
    BudgetAllocator,
    BudgetExhausted,
    CompositePlan,
    DependencyGraph,
    PlanStep,
    Provenance,
    RecoveryDegradedEvent,
    from_abstract_plan,
)
from src.ace.schema.abstract import AbstractPlan, AbstractTool


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
