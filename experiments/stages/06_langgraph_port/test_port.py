# ruff: noqa: N999
"""Contract tests for the LangGraph composite executor port."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from experiments.analysis.summarize_composite import false_value_propagated

STAGE_DIR = Path(__file__).resolve().parent
STAGE05_DIR = STAGE_DIR.parent / "05_composite"


def _load(name: str, path: Path) -> Any:
    module_spec = importlib.util.spec_from_file_location(name, path)
    assert module_spec is not None and module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[name] = module
    module_spec.loader.exec_module(module)
    return module


port = _load("wp2_langgraph_port", STAGE_DIR / "port.py")
sys.path.insert(0, str(STAGE05_DIR))
native_cases = _load("cases", STAGE05_DIR / "cases.py")
native_runner = _load("wp2_native_composite_runner", STAGE05_DIR / "run.py")


def _record(case_id: int) -> dict[str, object]:
    spec = port.CASES.build_case(case_id, "m2")
    return port.make_record(spec, 1, 0.0, port.execute_case(spec))


def test_reuses_stage05_case_seven_and_eight_specs() -> None:
    assert port.CASES.build_case(7, "m2").step_ids == ("A", "B", "C")
    assert port.CASES.build_case(8, "m2").edges == (("X", "Y"), ("X", "Z"))


@pytest.mark.parametrize("case_id", [7, 8])
def test_stategraph_nodes_and_edges_match_composite_dag(case_id: int) -> None:
    spec = port.CASES.build_case(case_id, "m2")
    executor = port.LangGraphCompositeExecutor(spec)
    graph = executor.compiled_graph.get_graph()
    plan_nodes = set(spec.step_ids)
    actual_edges = {(edge.source, edge.target) for edge in graph.edges if edge.source in plan_nodes and edge.target in plan_nodes}

    assert plan_nodes <= set(graph.nodes)
    assert actual_edges == set(spec.edges)


def test_case_seven_m2_outcome_matches_native_executor() -> None:
    langgraph = port.execute_case(port.CASES.build_case(7, "m2"))
    native = native_runner.execute_case(native_cases.build_case(7, "m2"))

    assert langgraph["outcome"] == native["outcome"]


def test_case_seven_m2_evidence_matches_native_executor() -> None:
    langgraph = port.execute_case(port.CASES.build_case(7, "m2"))
    native = native_runner.execute_case(native_cases.build_case(7, "m2"))

    assert langgraph["provenance"] == native["provenance"]
    assert langgraph["budget"] == native["budget"]
    assert langgraph["events"] == native["events"]


def test_case_seven_reconciles_all_thirty_trials() -> None:
    native_spec = native_cases.build_case(7, "m2")
    port_spec = port.CASES.build_case(7, "m2")
    for _ in range(30):
        langgraph = port.execute_case(port_spec)
        native = native_runner.execute_case(native_spec)
        assert langgraph["outcome"] == native["outcome"]
        assert langgraph["provenance"] == native["provenance"]
        assert langgraph["budget"] == native["budget"]
        assert langgraph["events"] == native["events"]


def test_record_has_schema_13_and_stage05_shape() -> None:
    record = _record(7)
    native_spec = native_cases.build_case(7, "m2")
    native = native_runner.make_record(native_spec, 1, 0.0, native_runner.execute_case(native_spec))

    assert record["schema_version"] == "1.3"
    assert set(record) == set(native)
    assert json.loads(json.dumps(record))["case_id"] == "case_7"


def test_case_eight_is_explicitly_degraded_in_all_thirty_trials() -> None:
    for trial in range(1, 31):
        record = port.make_record(
            port.CASES.build_case(8, "m2"),
            trial,
            0.0,
            port.execute_case(port.CASES.build_case(8, "m2")),
        )
        assert any(
            event["type"] == "recovery_degraded" and event.get("reason") == "recovery_budget_exhausted"
            for event in record["events"]
        )


def test_case_eight_has_zero_false_values_in_all_thirty_trials() -> None:
    for trial in range(1, 31):
        spec = port.CASES.build_case(8, "m2")
        record = port.make_record(spec, trial, 0.0, port.execute_case(spec))
        assert false_value_propagated(record) is False
        assert record["outcome"]["final_output"] is None


def test_case_eight_exhausts_only_the_shared_step_budget() -> None:
    result = port.execute_case(port.CASES.build_case(8, "m2"))

    assert result["budget"] == {
        "total": 1,
        "consumed": 1,
        "remaining": 0,
        "per_step_remaining": {"X": 0, "Y": 1, "Z": 1},
    }
