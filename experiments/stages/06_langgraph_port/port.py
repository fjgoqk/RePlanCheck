# ruff: noqa: N999
"""Run the deterministic WP2 composite cases through a LangGraph executor."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import operator
import sys
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Annotated, Any, TypedDict, cast
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, ValidationError

from ace.experiment_log import EXPERIMENT_SCHEMA_VERSION, current_git_commit
from ace.plan.composite import (
    BOTTOM,
    CompositePlan,
    CompositeRecovery,
    DependencyGraph,
    InputSlot,
    PlanStep,
    Provenance,
    RecoverySubstitutedEvent,
)
from ace.schema.abstract import AbstractPlan, AbstractTool
from ace.schema.concrete import ConcreteToolBase
from ace.schema.outcome import ExecutionVariant

STAGE_DIR = Path(__file__).resolve().parent
STAGE05_DIR = STAGE_DIR.parent / "05_composite"
CASES_PATH = STAGE05_DIR / "cases.py"


def _load_cases_module() -> Any:
    """Load the Stage 05 case specifications without modifying that stage."""
    module_name = "_wp2_langgraph_case_specs"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    module_spec = importlib.util.spec_from_file_location(module_name, CASES_PATH)
    if module_spec is None or module_spec.loader is None:
        raise ImportError(f"Cannot load composite cases from {CASES_PATH}")
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[module_name] = module
    module_spec.loader.exec_module(module)
    return module


CASES = _load_cases_module()


class GraphExecutionState(TypedDict):
    """Minimal merge-safe state shared by LangGraph plan-step nodes."""

    completed_steps: Annotated[list[str], operator.add]


class CompositeInput(BaseModel):
    values: tuple[float, ...] = ()


class CompositeOutput(BaseModel):
    value: float


class DeterministicTool(ConcreteToolBase):
    """Concrete descriptor used by the deterministic recovery policy."""

    def generate_source(self) -> str:
        return "def main(values=()):\n    return {'value': 1.0}\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run WP2 composite cases with LangGraph")
    parser.add_argument("--variant", choices=[item.value for item in ExecutionVariant], default="m2")
    parser.add_argument("--case", choices=["7", "8"], required=True)
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.trials < 1:
        parser.error("--trials must be at least 1")
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")
    return args


def _abstract_tool(step: Any) -> AbstractTool:
    return AbstractTool(
        name=step.tool_name,
        description=step.role,
        args_schema=CompositeInput,
        output_schema=CompositeOutput,
    )


def build_plan(spec: Any) -> tuple[CompositePlan, AbstractPlan]:
    """Build the same composite DAG and recovery baseline used by Stage 05."""
    graph = DependencyGraph()
    provenance = Provenance()
    abstract_tools: list[AbstractTool] = []
    for step_spec in spec.steps:
        tool = _abstract_tool(step_spec)
        abstract_tools.append(tool)
        inputs = {
            f"from_{source}": InputSlot.from_step(source, "value")
            for source, target in spec.edges
            if target == step_spec.id
        }
        if not inputs:
            inputs = {"request": InputSlot.external(spec.case_id)}
        graph.add_step(PlanStep(step_spec.id, tool, inputs=inputs, budget=step_spec.budget))
        provenance.add_source(step_spec.id, "value", Provenance.step_label(step_spec.id))
        if all(target != step_spec.id for _, target in spec.edges):
            provenance.add_source(step_spec.id, "value", Provenance.external_label())
    for source, target in spec.edges:
        graph.add_edge(source, target)

    script_lines = ["def main():"]
    for step in spec.steps:
        script_lines.append(f"    {step.id.lower()} = {step.tool_name}()")
    script_lines.append(f"    return {spec.steps[-1].id.lower()}")
    abstract_plan = AbstractPlan(script="\n".join(script_lines), abs_tools=abstract_tools)
    return CompositePlan(graph=graph, provenance=provenance, total_budget=spec.total_budget), abstract_plan


def _concrete_tool(name: str) -> DeterministicTool:
    return DeterministicTool(
        name=name,
        provider="wp2-deterministic",
        description=name,
        clearances={"public"},
        permissions=set(),
        args_schema=CompositeInput,
        output_schema=CompositeOutput,
    )


def _raw_output(behavior: str, value: float | None) -> object:
    if behavior == "schema_failure":
        return {"value": "not-a-number"}
    return {"value": 10.0 if value is None else value}


def _primary_output(step: Any, inputs: tuple[float, ...]) -> object:
    if step.primary_behavior != "ok" or not inputs:
        return _raw_output(step.primary_behavior, step.primary_value)
    if step.role == "join":
        return {"value": min(inputs)}
    if step.role in {"submit", "consumer"}:
        return {"value": inputs[0]}
    return _raw_output(step.primary_behavior, step.primary_value)


def _semantic_valid(step: Any, value: float) -> bool:
    return step.minimum_valid_value is None or value >= step.minimum_valid_value


def _json_value(value: object) -> object:
    if value is BOTTOM:
        return None
    if is_dataclass(value):
        return {key: _json_value(item) for key, item in asdict(cast(Any, value)).items()}
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_json_value(item) for item in value]
    if hasattr(value, "value"):
        return getattr(value, "value")
    return value


class LangGraphCompositeExecutor:
    """Execute a CompositePlan with one LangGraph node per plan step."""

    def __init__(self, spec: Any) -> None:
        self.spec = spec
        self.plan, self.abstract_plan = build_plan(spec)
        self.steps = {step.id: step for step in spec.steps}
        self.selected_tools = {step.tool_name: _concrete_tool(f"{step.tool_name}Primary") for step in spec.steps}
        self.substitutes = {
            step.tool_name: (_concrete_tool(f"{step.tool_name}Substitute"),)
            for step in spec.steps
            if step.substitute_behavior is not None
        }
        self.recovery = CompositeRecovery(
            self.plan,
            self.abstract_plan,
            self.selected_tools,
            self.substitutes,
            self._invoke_substitute,
        )
        self.events: list[dict[str, object]] = []
        self.tool_results: dict[str, dict[str, object]] = {}
        self.compiled_graph = self._compile_graph()

    def _compile_graph(self) -> CompiledStateGraph:
        builder = StateGraph(GraphExecutionState)
        for step_id in self.plan.graph.topological_sort():
            builder.add_node(step_id, self._node_for(step_id))
        for source, target in sorted(self.plan.graph.edges):
            builder.add_edge(source, target)
        roots = [step_id for step_id in self.plan.graph.steps if not self.plan.graph.fan_in(step_id)]
        terminals = [step_id for step_id in self.plan.graph.steps if not self.plan.graph.fan_out(step_id)]
        for step_id in roots:
            builder.add_edge(START, step_id)
        for step_id in terminals:
            builder.add_edge(step_id, END)
        return builder.compile()

    def _node_for(self, step_id: str) -> Any:
        def execute_step(state: GraphExecutionState) -> GraphExecutionState:
            del state
            self._execute_step(step_id)
            return {"completed_steps": [step_id]}

        return execute_step

    def _event(self, event_type: str, step_id: str, **details: object) -> None:
        self.events.append({"sequence": len(self.events) + 1, "type": event_type, "step_id": step_id, **details})

    def _invoke_substitute(self, tool: ConcreteToolBase, inputs: Mapping[str, Any]) -> object:
        del inputs
        step = next(item for item in self.spec.steps if f"{item.tool_name}Substitute" == tool.name)
        return _raw_output(step.substitute_behavior or "schema_failure", step.substitute_value)

    def _input_values(self, step_id: str) -> tuple[float, ...] | None:
        values: list[float] = []
        for source in sorted(self.plan.graph.fan_in(step_id)):
            value = self.plan.output_slots.get((source, "value"), BOTTOM)
            if value is BOTTOM:
                return None
            values.append(float(value))
        return tuple(values)

    def _write_primary(self, step: Any, value: float, *, poisoned: bool = False) -> None:
        self.plan.output_slots[(step.id, "value")] = value
        self.plan.provenance.add_source(step.id, "value", Provenance.step_label(step.id))
        if not self.plan.graph.fan_in(step.id):
            self.plan.provenance.add_source(step.id, "value", Provenance.external_label())
        if poisoned:
            self.plan.provenance.add_source(
                step.id,
                "value",
                Provenance.substitute_label(f"poisoned_{step.tool_name}"),
            )

    def _recover(self, step: Any, raw: object, inputs: tuple[float, ...]) -> object:
        self._event("recovery_requested", step.id)
        result = self.recovery.recover(step.id, raw, {"values": inputs}, affected_fields=("value",))
        recovery_event = self.recovery.events[-1]
        if isinstance(recovery_event, RecoverySubstitutedEvent):
            self._event(
                "recovery_substituted",
                step.id,
                replacement_tool=recovery_event.replacement_tool,
            )
        else:
            self._event("recovery_degraded", step.id, reason=recovery_event.reason)
        return result

    def _execute_step(self, step_id: str) -> None:
        step = self.steps[step_id]
        inputs = self._input_values(step_id)
        if inputs is None:
            self.plan.degrade(step_id, "upstream_unavailable")
            self._event("step_skipped", step_id, reason="upstream_unavailable")
            self.tool_results[step.tool_name] = {"status": "failed", "value": None}
            return

        self._event("step_started", step_id)
        raw = _primary_output(step, inputs)
        validated_value: float | None = None
        try:
            validated_value = CompositeOutput.model_validate(raw).value
            schema_valid = True
        except ValidationError:
            schema_valid = False
        semantic_valid = schema_valid and validated_value is not None and _semantic_valid(step, validated_value)

        if schema_valid and semantic_valid:
            assert validated_value is not None
            self._write_primary(step, validated_value)
            self.tool_results[step.tool_name] = {"status": "success", "value": {"value": validated_value}}
            self._event("step_completed", step_id)
            return

        poisoned = schema_valid and not semantic_valid
        if poisoned:
            assert validated_value is not None
            self._write_primary(step, validated_value, poisoned=True)
        self.tool_results[step.tool_name] = {"status": "rejected", "value": None}
        self._event("step_rejected", step_id, boundary="semantic_predicate" if poisoned else "output_schema")

        if self.spec.variant is ExecutionVariant.BASELINE:
            self.plan.degrade(step_id, "baseline_abort")
            self._event("execution_aborted", step_id, reason="baseline_abort")
            return
        if self.spec.variant is ExecutionVariant.M0:
            self._write_primary(step, 0.0)
            self._event("legacy_fallback", step_id, value=0.0)
            return
        if self.spec.variant is ExecutionVariant.M1:
            self.plan.degrade(step_id, "structured_unavailable")
            self._event("recovery_degraded", step_id, reason="structured_unavailable")
            return

        recovered = self._recover(step, raw, inputs)
        if recovered is BOTTOM:
            return
        if not isinstance(recovered, dict):
            raise TypeError("Composite recovery returned a non-mapping result")
        recovered_value = float(recovered["value"])
        self.tool_results[f"{step.tool_name}Substitute"] = {
            "status": "success",
            "value": {"value": recovered_value},
        }
        if _semantic_valid(step, recovered_value):
            return

        self._event("step_rejected", step_id, boundary="semantic_predicate_after_substitution")
        recovered_again = self._recover(step, recovered, inputs)
        if recovered_again is BOTTOM:
            self.tool_results[f"{step.tool_name}Substitute"] = {"status": "rejected", "value": None}

    def execute(self) -> dict[str, object]:
        state = self.compiled_graph.invoke({"completed_steps": []})
        if set(state["completed_steps"]) != set(self.plan.graph.steps):
            raise RuntimeError("LangGraph did not execute every plan-step node")

        self.plan.provenance.propagate(self.plan.graph)
        terminal_ids = [step_id for step_id in self.plan.graph.steps if not self.plan.graph.fan_out(step_id)]
        terminal_values = [self.plan.output_slots.get((step_id, "value"), BOTTOM) for step_id in terminal_ids]
        final_output = terminal_values[-1] if terminal_values and all(value is not BOTTOM for value in terminal_values) else None
        degraded = any(event["type"] in {"recovery_degraded", "step_skipped"} for event in self.events)
        aborted = any(event["type"] == "execution_aborted" for event in self.events)
        status = "failed" if aborted else "partial_success" if degraded or final_output is None else "success"
        return {
            "status": status,
            "final_output": final_output,
            "tool_results": self.tool_results,
            "failures": [],
            "repairs": [
                _json_value(event.patch)
                for event in self.recovery.events
                if isinstance(event, RecoverySubstitutedEvent)
            ],
        }

    def evidence(self) -> tuple[dict[str, list[str]], dict[str, object], list[dict[str, object]]]:
        provenance = {step.id: sorted(self.plan.provenance.sources_for(step.id, "value")) for step in self.spec.steps}
        allocator = self.plan.budget_allocator
        budget = {
            "total": self.plan.total_budget,
            "consumed": allocator.consumed,
            "remaining": allocator.remaining,
            "per_step_remaining": {step.id: allocator.remaining_for(step.id) for step in self.spec.steps},
        }
        return provenance, budget, self.events


def execute_case(spec: Any) -> dict[str, object]:
    """Execute one Stage 05 case specification on LangGraph."""
    started = monotonic()
    executor = LangGraphCompositeExecutor(spec)
    outcome = executor.execute()
    duration_ms = round((monotonic() - started) * 1000)
    provenance, budget, events = executor.evidence()
    return {
        "duration_ms": duration_ms,
        "outcome": outcome,
        "provenance": provenance,
        "budget": budget,
        "events": events,
    }


def make_record(spec: Any, trial: int, temperature: float, result: dict[str, object]) -> dict[str, object]:
    """Build a schema-1.3 JSONL record matching the Stage 05 record shape."""
    query = f"Execute WP2 composite Case {spec.case_id}: {spec.description}"
    plan_text = json.dumps({"steps": spec.step_ids, "edges": spec.edges}, separators=(",", ":"))
    return {
        "schema_version": EXPERIMENT_SCHEMA_VERSION,
        "run_id": str(uuid4()),
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "query": query,
        "query_sha256": hashlib.sha256(query.encode()).hexdigest(),
        "llm_model": "deterministic-langgraph-composite",
        "embedding_model": "none",
        "tool_manifest": "experiments/stages/05_composite/cases.py",
        "temperature": temperature,
        "duration_ms": result["duration_ms"],
        "git_commit": current_git_commit(),
        "variant": spec.variant.value,
        "case_id": f"case_{spec.case_id}",
        "trial": trial,
        "attack_type": spec.attack_type,
        "plan_fixture": "experiments/stages/05_composite/cases.py",
        "plan_digest": hashlib.sha256(plan_text.encode()).hexdigest(),
        "expected_tools": [step.tool_name for step in spec.steps],
        "mapped_tools": [f"{step.tool_name}Primary" for step in spec.steps],
        "recovery_manifest": None,
        "approved_substitutions": {
            step.tool_name: [f"{step.tool_name}Substitute"]
            for step in spec.steps
            if step.substitute_behavior is not None
        },
        "outcome": result["outcome"],
        "provenance": result["provenance"],
        "budget": result["budget"],
        "events": result["events"],
    }


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    spec = CASES.build_case(args.case, args.variant)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        for trial in range(1, args.trials + 1):
            record = make_record(spec, trial, args.temperature, execute_case(spec))
            output.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            outcome = record["outcome"]
            if not isinstance(outcome, dict):
                raise TypeError("Experiment outcome must be a mapping")
            print(
                json.dumps(
                    {
                        "run_id": record["run_id"],
                        "case_id": record["case_id"],
                        "trial": trial,
                        "status": outcome["status"],
                        "duration_ms": record["duration_ms"],
                    },
                    separators=(",", ":"),
                )
            )


if __name__ == "__main__":
    main()
