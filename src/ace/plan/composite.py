"""Core data structures for composite abstract plans."""

from __future__ import annotations

import ast
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from ..recovery import RepairPolicy
from ..schema.abstract import AbstractPlan, AbstractTool
from ..schema.concrete import ConcreteToolBase
from ..schema.recovery import FailureKind, RepairPatch, ToolFailure


class BudgetExhausted(RuntimeError):  # noqa: N818 - public API name required by the recovery protocol
    """Raised when a plan step has no recovery budget available."""


@dataclass(frozen=True)
class RecoveryDegradedEvent:
    """Record that a plan step must continue through its degraded path."""

    step_id: str
    reason: str = "recovery_budget_exhausted"


@dataclass(frozen=True)
class RecoverySubstitutedEvent:
    """Record a verified replacement whose output was written back to a step."""

    step_id: str
    replacement_tool: str
    failure: ToolFailure
    patch: RepairPatch


class _Bottom:
    """Unforgeable marker for a step that has no validated output."""

    def __repr__(self) -> str:
        return "⊥"


BOTTOM = _Bottom()


@dataclass(frozen=True)
class InputSlot:
    """Describe a step input supplied externally or by an upstream step."""

    kind: Literal["external", "step"]
    value: Any = None
    step_id: str | None = None
    output: str | None = None

    @classmethod
    def external(cls, value: Any) -> InputSlot:
        """Create a slot whose value comes from outside the composite plan."""
        return cls(kind="external", value=value)

    @classmethod
    def from_step(cls, step_id: str, output: str | None = None) -> InputSlot:
        """Create a slot that references an upstream step output."""
        return cls(kind="step", step_id=step_id, output=output)


@dataclass
class PlanStep:
    """Represent one abstract-tool invocation in a composite plan."""

    id: str
    tool: AbstractTool
    inputs: dict[str, InputSlot] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    budget: int = 1

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Plan step id must not be empty")
        if self.budget < 0:
            raise ValueError("Recovery budget must be non-negative")


class DependencyGraph:
    """Store plan steps and directed data dependencies between them."""

    def __init__(self) -> None:
        self.steps: dict[str, PlanStep] = {}
        self._successors: dict[str, set[str]] = {}
        self._predecessors: dict[str, set[str]] = {}

    @property
    def edges(self) -> set[tuple[str, str]]:
        """Return dependency edges as ``(upstream, downstream)`` pairs."""
        return {(source, target) for source, targets in self._successors.items() for target in targets}

    def add_step(self, step: PlanStep) -> None:
        """Add a uniquely identified step node."""
        if step.id in self.steps:
            raise ValueError(f"Duplicate plan step id: {step.id}")
        self.steps[step.id] = step
        self._successors[step.id] = set()
        self._predecessors[step.id] = set()

    def add_edge(self, source: str | PlanStep, target: str | PlanStep) -> None:
        """Add a directed data dependency from an upstream to a downstream step."""
        source_id = source.id if isinstance(source, PlanStep) else source
        target_id = target.id if isinstance(target, PlanStep) else target
        missing = [step_id for step_id in (source_id, target_id) if step_id not in self.steps]
        if missing:
            raise KeyError(f"Unknown plan step: {', '.join(missing)}")
        if source_id == target_id:
            raise ValueError(f"Dependency graph contains a cycle involving {source_id}")
        self._successors[source_id].add(target_id)
        self._predecessors[target_id].add(source_id)

    def topological_sort(self) -> list[str]:
        """Return step ids in dependency order, raising when the graph is cyclic."""
        indegree = {step_id: len(sources) for step_id, sources in self._predecessors.items()}
        ready = deque(step_id for step_id in self.steps if indegree[step_id] == 0)
        ordered: list[str] = []

        while ready:
            step_id = ready.popleft()
            ordered.append(step_id)
            for target in self._successors[step_id]:
                indegree[target] -= 1
                if indegree[target] == 0:
                    ready.append(target)

        if len(ordered) != len(self.steps):
            cyclic = sorted(step_id for step_id, degree in indegree.items() if degree > 0)
            raise ValueError(f"Dependency graph contains a cycle: {', '.join(cyclic)}")
        return ordered

    def topological_steps(self) -> list[PlanStep]:
        """Return step objects in dependency order."""
        return [self.steps[step_id] for step_id in self.topological_sort()]

    def has_cycle(self) -> bool:
        """Return whether the graph contains a directed cycle."""
        try:
            self.topological_sort()
        except ValueError:
            return True
        return False

    def fan_in(self, step: str | PlanStep) -> set[str]:
        """Return the immediate upstream step ids for a node."""
        step_id = self._require_step(step)
        return set(self._predecessors[step_id])

    def fan_out(self, step: str | PlanStep) -> set[str]:
        """Return the immediate downstream step ids for a node."""
        step_id = self._require_step(step)
        return set(self._successors[step_id])

    def is_reachable(self, source: str | PlanStep, target: str | PlanStep) -> bool:
        """Return whether a non-empty directed path connects two steps."""
        source_id = self._require_step(source)
        target_id = self._require_step(target)
        pending = list(self._successors[source_id])
        visited: set[str] = set()
        while pending:
            current = pending.pop()
            if current == target_id:
                return True
            if current not in visited:
                visited.add(current)
                pending.extend(self._successors[current])
        return False

    def _require_step(self, step: str | PlanStep) -> str:
        step_id = step.id if isinstance(step, PlanStep) else step
        if step_id not in self.steps:
            raise KeyError(f"Unknown plan step: {step_id}")
        return step_id


class Provenance:
    """Track and propagate source labels for each step output."""

    def __init__(self) -> None:
        self._sources: dict[tuple[str, str], set[str]] = {}

    def add_source(self, step_id: str, output: str, label: str) -> None:
        """Attach one source label to a step output."""
        self._validate_label(label)
        self._sources.setdefault((step_id, output), set()).add(label)

    def set_sources(self, step_id: str, output: str, labels: set[str]) -> None:
        """Replace the source labels attached to a step output."""
        for label in labels:
            self._validate_label(label)
        self._sources[(step_id, output)] = set(labels)

    def sources_for(self, step_id: str, output: str = "result") -> set[str]:
        """Return a copy of the source labels for a step output."""
        return set(self._sources.get((step_id, output), set()))

    def propagate(self, graph: DependencyGraph) -> None:
        """Propagate all upstream output labels through dependency edges."""
        for step_id in graph.topological_sort():
            inherited: set[str] = set()
            for upstream_id in graph.fan_in(step_id):
                for (source_id, _), labels in self._sources.items():
                    if source_id == upstream_id:
                        inherited.update(labels)

            output_names = {output for source_id, output in self._sources if source_id == step_id} or {"result"}
            for output in output_names:
                self._sources.setdefault((step_id, output), set()).update(inherited)
                self._sources[(step_id, output)].add(f"step:{step_id}")

    @staticmethod
    def external_label() -> str:
        """Return the canonical external-input source label."""
        return "external"

    @staticmethod
    def step_label(step_id: str) -> str:
        """Return the canonical source label for a plan step."""
        return f"step:{step_id}"

    @staticmethod
    def substitute_label(tool: str | AbstractTool | ConcreteToolBase) -> str:
        """Return the canonical source label for a substitute tool."""
        tool_name = tool if isinstance(tool, str) else tool.name
        return f"substitute:{tool_name}"

    @staticmethod
    def _validate_label(label: str) -> None:
        if label == "external" or label.startswith("step:") or label.startswith("substitute:"):
            return
        raise ValueError(f"Invalid provenance label: {label}")


@dataclass
class CompositePlan:
    """Bundle a dependency graph, provenance, and bounded recovery state."""

    graph: DependencyGraph = field(default_factory=DependencyGraph)
    provenance: Provenance = field(default_factory=Provenance)
    output_slots: dict[tuple[str, str], Any] = field(default_factory=dict)
    total_budget: int | None = None
    _budget_allocator: BudgetAllocator = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._budget_allocator = BudgetAllocator(self, self.total_budget)
        self.total_budget = self._budget_allocator.total_budget

    @property
    def budget_allocator(self) -> BudgetAllocator:
        """Return the recovery budget allocator owned by this plan."""
        return self._budget_allocator

    @property
    def recovery_events(self) -> tuple[RecoveryDegradedEvent, ...]:
        """Return immutable degradation records in occurrence order."""
        return self._budget_allocator.events

    def can_recover(self, step: str | PlanStep) -> bool:
        """Return whether a step may make another bounded recovery attempt."""
        return self._budget_allocator.can_recover(step)

    def consume_for(self, step: str | PlanStep) -> int:
        """Consume one recovery attempt for a step and return its remaining budget."""
        return self._budget_allocator.consume(step)

    def degrade(
        self,
        step: str | PlanStep,
        reason: str = "recovery_budget_exhausted",
    ) -> RecoveryDegradedEvent:
        """Permanently route a step to its degraded path and record the decision."""
        return self._budget_allocator.degrade(step, reason)

    def output_for(self, step: str | PlanStep, output: str = "result") -> Any:
        """Return a value previously written to a step output slot."""
        step_id = step.id if isinstance(step, PlanStep) else step
        if step_id not in self.graph.steps:
            raise KeyError(f"Unknown plan step: {step_id}")
        return self.output_slots[(step_id, output)]

    @classmethod
    def from_abstract_plan(cls, plan: AbstractPlan) -> CompositePlan:
        """Convert an existing abstract plan into a composite plan."""
        return from_abstract_plan(plan)


class BudgetAllocator:
    """Allocate and consume bounded recovery attempts for a ``CompositePlan``.

    The allocator enforces two limits at all times: a step cannot consume more
    than its own ``PlanStep.budget``, and total consumption cannot exceed
    ``total_budget``. Unused budget from one step never permits another step to
    overspend its allocation.
    """

    def __init__(self, plan: CompositePlan, total_budget: int | None = None) -> None:
        step_budgets = {step_id: step.budget for step_id, step in plan.graph.steps.items()}
        if total_budget is None:
            total_budget = sum(step_budgets.values())
        if total_budget < 0:
            raise ValueError("Total recovery budget must be non-negative")

        self._plan = plan
        self.total_budget = total_budget
        self._remaining_by_step = step_budgets
        self._consumed = 0
        self._degraded: set[str] = set()
        self._events: list[RecoveryDegradedEvent] = []

    @property
    def consumed(self) -> int:
        """Return the number of recovery attempts consumed across the plan."""
        return self._consumed

    @property
    def remaining(self) -> int:
        """Return the unused portion of the global recovery budget."""
        return self.total_budget - self._consumed

    @property
    def events(self) -> tuple[RecoveryDegradedEvent, ...]:
        """Return immutable degradation records in occurrence order."""
        return tuple(self._events)

    def remaining_for(self, step: str | PlanStep) -> int:
        """Return the unconsumed per-step recovery budget."""
        return self._remaining_by_step[self._step_id(step)]

    def can_recover(self, step: str | PlanStep) -> bool:
        """Return whether both the step and global budgets allow recovery."""
        step_id = self._step_id(step)
        return step_id not in self._degraded and self._remaining_by_step[step_id] > 0 and self.remaining > 0

    def consume(self, step: str | PlanStep) -> int:
        """Consume one attempt and return the step budget remaining afterward."""
        step_id = self._step_id(step)
        if not self.can_recover(step_id):
            raise BudgetExhausted(f"Recovery budget exhausted for plan step {step_id}")

        self._remaining_by_step[step_id] -= 1
        self._consumed += 1
        return self._remaining_by_step[step_id]

    def consume_for(self, step: str | PlanStep) -> int:
        """Consume one recovery attempt through the orchestration-facing API."""
        return self.consume(step)

    def degrade(
        self,
        step: str | PlanStep,
        reason: str = "recovery_budget_exhausted",
    ) -> RecoveryDegradedEvent:
        """Permanently disable recovery for a step and record that decision."""
        step_id = self._step_id(step)
        self._degraded.add(step_id)
        event = RecoveryDegradedEvent(step_id=step_id, reason=reason)
        self._events.append(event)
        return event

    def _step_id(self, step: str | PlanStep) -> str:
        step_id = step.id if isinstance(step, PlanStep) else step
        if step_id not in self._remaining_by_step:
            raise KeyError(f"Unknown plan step: {step_id}")
        return step_id


RecoveryInvoker = Callable[[ConcreteToolBase, Mapping[str, Any]], object]


class CompositeRecovery:
    """Apply bounded, pre-authorized WP1 substitution to a composite plan.

    ``approved_substitutions`` is the launch-time recovery set. Its members are
    treated as read-only and idempotent by the caller's pre-authorization; this
    class rechecks the machine-representable schema, clearance, and permission
    constraints before asking :class:`RepairPolicy` to authorize a patch.
    """

    def __init__(
        self,
        plan: CompositePlan,
        abstract_plan: AbstractPlan,
        selected_tools: Mapping[str, ConcreteToolBase],
        approved_substitutions: Mapping[str, Sequence[ConcreteToolBase]],
        invoke: RecoveryInvoker,
        repair_policy: RepairPolicy | None = None,
    ) -> None:
        self.plan = plan
        self.abstract_plan = abstract_plan
        self.selected_tools = dict(selected_tools)
        self.approved_substitutions = {name: tuple(substitutes) for name, substitutes in approved_substitutions.items()}
        self.invoke = invoke
        self.repair_policy = repair_policy or RepairPolicy()
        self.repair_policy.arm_baseline(abstract_plan, self.selected_tools)
        self._events: list[RecoverySubstitutedEvent | RecoveryDegradedEvent] = []

    @property
    def events(self) -> tuple[RecoverySubstitutedEvent | RecoveryDegradedEvent, ...]:
        """Return substitution and degradation records in occurrence order."""
        return tuple(self._events)

    def recover(
        self,
        step: str | PlanStep,
        unverified_output: object,
        inputs: Mapping[str, Any],
        *,
        affected_fields: tuple[str, ...] = (),
        failure_kind: FailureKind | str = FailureKind.OUTPUT_SCHEMA_VALIDATION,
    ) -> object:
        """Recover one H1 output failure, or write ``BOTTOM`` on degradation."""
        plan_step = self._step(step)
        if not self._is_h1(failure_kind):
            return self._degrade(plan_step, "failure_not_h1")
        if not self.plan.can_recover(plan_step):
            return self._degrade(plan_step, "recovery_budget_exhausted")

        selected = self.selected_tools.get(plan_step.tool.name)
        substitutes = self.approved_substitutions.get(plan_step.tool.name, ())
        replacement = next(
            (candidate for candidate in substitutes if selected and self._eligible(selected, candidate)),
            None,
        )
        if selected is None or replacement is None:
            return self._degrade(plan_step, "no_approved_substitute")

        approved_names = tuple(sorted({selected.name, *(tool.name for tool in substitutes)}))
        approved_permissions = tuple(
            sorted(
                f"{tool.name}:{permission.value}"
                for tool in (selected, *substitutes)
                for permission in tool.permissions
            )
        )
        try:
            failure, patch = self.repair_policy.propose_substitution(
                plan=self.abstract_plan,
                tools=self.selected_tools,
                abstract_tool=plan_step.tool.name,
                concrete_tool=selected,
                replacement_tool=replacement,
                approved_tools=approved_names,
                approved_permissions=approved_permissions,
                output=unverified_output,
                affected_fields=affected_fields,
            )
            raw_output = self.invoke(replacement, inputs)
            validated = plan_step.tool.output_schema.model_validate(raw_output)
        except Exception:
            return self._degrade(plan_step, "substitution_failed")

        self.plan.consume_for(plan_step)
        values = validated.model_dump()
        label = Provenance.substitute_label(replacement.name)
        for output_name, value in values.items():
            self.plan.output_slots[(plan_step.id, output_name)] = value
            self.plan.provenance.add_source(plan_step.id, output_name, label)
        event = RecoverySubstitutedEvent(
            step_id=plan_step.id,
            replacement_tool=replacement.name,
            failure=failure,
            patch=patch,
        )
        self._events.append(event)
        return values

    def _degrade(self, step: PlanStep, reason: str) -> _Bottom:
        event = self.plan.degrade(step, reason)
        self._events.append(event)
        output_names = tuple(step.tool.output_schema.model_fields) or ("result",)
        for output_name in output_names:
            self.plan.output_slots[(step.id, output_name)] = BOTTOM
        return BOTTOM

    def _step(self, step: str | PlanStep) -> PlanStep:
        step_id = step.id if isinstance(step, PlanStep) else step
        try:
            return self.plan.graph.steps[step_id]
        except KeyError:
            raise KeyError(f"Unknown plan step: {step_id}") from None

    @staticmethod
    def _is_h1(failure_kind: FailureKind | str) -> bool:
        return failure_kind in {FailureKind.OUTPUT_SCHEMA_VALIDATION, "H1"}

    @staticmethod
    def _eligible(selected: ConcreteToolBase, replacement: ConcreteToolBase) -> bool:
        if selected.name == replacement.name:
            return False
        if selected.clearances != replacement.clearances:
            return False
        if not replacement.permissions.issubset(selected.permissions):
            return False
        return CompositeRecovery._schema_equal(
            selected.args_schema, replacement.args_schema
        ) and CompositeRecovery._schema_equal(selected.output_schema, replacement.output_schema)

    @staticmethod
    def _schema_equal(left: type[Any] | None, right: type[Any] | None) -> bool:
        if left is None or right is None:
            return left is right
        return left.model_json_schema() == right.model_json_schema()


@dataclass(frozen=True)
class _Binding:
    step_id: str
    output: str | None = None


def from_abstract_plan(plan: AbstractPlan) -> CompositePlan:
    """Convert abstract-tool calls and their data dependencies from an AbstractPlan."""
    graph = DependencyGraph()
    provenance = Provenance()
    tools = {tool.name: tool for tool in plan.abs_tools}
    bindings: dict[str, _Binding] = {}

    calls: list[ast.Call] = []
    for node in ast.walk(ast.parse(plan.script)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in tools:
            calls.append(node)
    calls.sort(key=lambda node: (node.lineno, node.col_offset))

    for index, call in enumerate(calls, start=1):
        if not isinstance(call.func, ast.Name):
            continue
        tool = tools[call.func.id]
        step_id = f"step_{index}"
        inputs: dict[str, InputSlot] = {}
        dependencies: set[str] = set()

        for position, argument in enumerate(call.args):
            slot = _input_slot(argument, bindings)
            inputs[f"arg{position}"] = slot
            if slot.step_id:
                dependencies.add(slot.step_id)
        for keyword in call.keywords:
            name = keyword.arg or "kwargs"
            slot = _input_slot(keyword.value, bindings)
            inputs[name] = slot
            if slot.step_id:
                dependencies.add(slot.step_id)

        step = PlanStep(
            id=step_id,
            tool=tool,
            inputs=inputs,
            metadata={"line": call.lineno},
        )
        graph.add_step(step)
        for dependency in dependencies:
            graph.add_edge(dependency, step_id)

        output_names = list(tool.output_schema.model_fields) or ["result"]
        has_external_input = any(slot.kind == "external" for slot in inputs.values())
        for output_name in output_names:
            provenance.add_source(step_id, output_name, Provenance.step_label(step_id))
            if has_external_input:
                provenance.add_source(step_id, output_name, Provenance.external_label())

        parent = _parent_assignment(plan.script, call)
        if parent is not None:
            bindings[parent] = _Binding(step_id)

    provenance.propagate(graph)
    return CompositePlan(graph=graph, provenance=provenance)


def _input_slot(expression: ast.expr, bindings: dict[str, _Binding]) -> InputSlot:
    references = _binding_references(expression, bindings)
    if references:
        binding = references[0]
        return InputSlot.from_step(binding.step_id, binding.output)
    try:
        value = ast.literal_eval(expression)
    except (ValueError, TypeError):
        value = ast.unparse(expression)
    return InputSlot.external(value)


def _binding_references(expression: ast.expr, bindings: dict[str, _Binding]) -> list[_Binding]:
    references: list[_Binding] = []
    for node in ast.walk(expression):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in bindings:
            binding = bindings[node.value.id]
            references.append(_Binding(binding.step_id, node.attr))
        elif isinstance(node, ast.Name) and node.id in bindings:
            references.append(bindings[node.id])
    return references


def _parent_assignment(script: str, target_call: ast.Call) -> str | None:
    tree = ast.parse(script)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            value = node.value
            target = node.targets[0]
        elif isinstance(node, ast.AnnAssign):
            value = node.value
            target = node.target
        else:
            continue
        if not isinstance(value, ast.Call) or (value.lineno, value.col_offset) != (
            target_call.lineno,
            target_call.col_offset,
        ):
            continue
        if isinstance(target, ast.Name):
            return target.id
    return None
