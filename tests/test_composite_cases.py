from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from ace.plan.composite import DependencyGraph, PlanStep

STAGE_DIR = Path(__file__).parents[1] / "experiments" / "stages" / "05_composite"
sys.path.insert(0, str(STAGE_DIR))


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, STAGE_DIR / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


cases = _load("wp2_composite_cases", "cases.py")
runner = _load("wp2_composite_run", "run.py")


def test_case_numbers_continue_with_seven_eight_and_nine():
    specs = cases.build_cases("baseline")

    assert [spec.case_id for spec in specs] == [7, 8, 9]
    assert [spec.attack_type for spec in specs] == [
        "composite_chain_poison",
        "composite_budget_exhaustion",
        "composite_a2_semantic_poison",
    ]


@pytest.mark.parametrize("variant", ["baseline", "m0", "m1", "m2"])
def test_case_nine_has_comparable_four_variant_specifications(variant):
    spec = cases.build_case(9, variant)

    assert spec.variant.value == variant
    assert spec.step_ids == ("A", "B", "A2", "C")
    assert spec.edges == (("A", "B"), ("A", "A2"), ("B", "C"), ("A2", "C"))


def test_case_graph_cycle_is_detected():
    spec = cases.build_case(7, "m2")
    plan, _ = runner.build_plan(spec)
    cyclic = DependencyGraph()
    for step in plan.graph.steps.values():
        cyclic.add_step(PlanStep(step.id, step.tool))
    cyclic.add_edge("A", "B")
    cyclic.add_edge("B", "C")
    cyclic.add_edge("C", "A")

    assert cyclic.has_cycle()
    with pytest.raises(ValueError, match="contains a cycle"):
        cyclic.topological_sort()


def test_case_seven_poison_source_propagates_to_submit_step():
    result = runner.execute_case(cases.build_case(7, "m2"))

    assert "substitute:poisoned_ComputeValue" in result["provenance"]["B"]
    assert "substitute:poisoned_ComputeValue" in result["provenance"]["C"]
    assert "substitute:ComputeValueSubstitute" in result["provenance"]["C"]
    assert result["outcome"]["final_output"] == 25.0


def test_case_seven_baseline_stops_at_semantic_predicate():
    result = runner.execute_case(cases.build_case(7, "baseline"))

    assert result["outcome"]["status"] == "failed"
    assert result["outcome"]["final_output"] is None
    assert [event["type"] for event in result["events"]][-2:] == [
        "step_rejected",
        "execution_aborted",
    ]
    assert result["events"][-2]["boundary"] == "semantic_predicate"
    assert "substitute:poisoned_ComputeValue" in result["provenance"]["C"]


def test_case_eight_exhausts_budget_and_degrades_without_false_values():
    result = runner.execute_case(cases.build_case(8, "m2"))

    assert result["budget"] == {
        "total": 1,
        "consumed": 1,
        "remaining": 0,
        "per_step_remaining": {"X": 0, "Y": 1, "Z": 1},
    }
    assert result["outcome"]["final_output"] is None
    assert result["outcome"]["tool_results"]["FirstConsumer"]["value"] is None
    assert result["outcome"]["tool_results"]["SecondConsumer"]["value"] is None
    assert result["events"][-3]["type"] == "recovery_degraded"
    assert result["events"][-3]["reason"] == "recovery_budget_exhausted"


def test_event_sequence_is_contiguous_and_orders_recovery():
    result = runner.execute_case(cases.build_case(7, "m2"))
    events = result["events"]
    event_types = [event["type"] for event in events]

    assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
    assert event_types.index("step_rejected") < event_types.index("recovery_requested")
    assert event_types.index("recovery_requested") < event_types.index("recovery_substituted")


@pytest.mark.parametrize(
    ("variant", "status", "final_output"),
    [
        ("baseline", "failed", None),
        ("m0", "partial_success", 0.0),
        ("m1", "partial_success", None),
        ("m2", "success", 0.01),
    ],
)
def test_case_nine_preserves_existing_variant_semantics(variant, status, final_output):
    result = runner.execute_case(cases.build_case(9, variant))

    assert result["outcome"]["status"] == status
    assert result["outcome"]["final_output"] == final_output


def test_case_nine_m2_records_poisoned_substitute_provenance():
    result = runner.execute_case(cases.build_case(9, "m2"))

    assert "substitute:RiskyQuoteSubstitute" in result["provenance"]["A2"]
    assert "substitute:RiskyQuoteSubstitute" in result["provenance"]["C"]
    assert result["budget"]["consumed"] == 1


def test_record_is_json_serializable_and_contains_composite_evidence():
    spec = cases.build_case(7, "baseline")
    record = runner.make_record(spec, 1, 0.0, runner.execute_case(spec))

    parsed = json.loads(json.dumps(record))
    assert parsed["schema_version"] == "1.3"
    assert parsed["case_id"] == "case_7"
    assert isinstance(parsed["duration_ms"], int)
    assert {"provenance", "budget", "events"}.issubset(parsed)
