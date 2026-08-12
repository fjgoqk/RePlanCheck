from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.ace.plan.fixture import FixtureAbstractPlanner, PlanFixture

FIXTURE_PATH = Path("experiments/fixtures/case_studies/fare_comparison.json")


def test_plan_fixture_builds_stable_two_tool_plan():
    fixture = PlanFixture.load(FIXTURE_PATH)
    plan = fixture.to_abstract_plan()
    protocol = plan.compile_for_protocol()

    assert fixture.fixture_id == "case-studies-fare-comparison-v1"
    assert fixture.plan_digest == "6552751c1dcaf9453f25f69bc9f969f3159c119b6b0afdd873acd11c85164a47"
    assert [tool.name for tool in plan.abs_tools] == ["QuickRideFareEstimate", "MetroHailFareEstimate"]
    assert fixture.expected_tools == ["QuickRide", "MetroHail"]
    assert "'QuickRideFareEstimate'" in protocol
    assert "'MetroHailFareEstimate'" in protocol


def test_fixture_planner_enforces_exact_query_and_runs_analysis():
    fixture = PlanFixture.load(FIXTURE_PATH)
    analyzer = MagicMock()
    planner = FixtureAbstractPlanner(fixture, analyzer=analyzer)

    plan = planner.generate_abstract_plan(fixture.query)

    analyzer.analyze_post_abstract_tools.assert_called_once_with(plan.abs_tools)
    analyzer.analyze_post_abstract_plan.assert_called_once_with(plan)
    with pytest.raises(ValueError, match="does not match deterministic fixture"):
        planner.generate_abstract_plan("different query")
