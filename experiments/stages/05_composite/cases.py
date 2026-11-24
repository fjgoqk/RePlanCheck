"""Specifications for the three WP2 composite attack cases."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from ace.schema.outcome import ExecutionVariant

Behavior = Literal["ok", "schema_failure", "semantic_poison"]


@dataclass(frozen=True)
class StepSpec:
    """One deterministic step in a composite experiment case."""

    id: str
    tool_name: str
    role: str
    primary_behavior: Behavior = "ok"
    primary_value: float = 10.0
    substitute_behavior: Behavior | None = None
    substitute_value: float | None = None
    minimum_valid_value: float | None = None
    budget: int = 1


@dataclass(frozen=True)
class CompositeCaseSpec:
    """A variant-specific composite case with explicit acceptance criteria."""

    case_id: int
    name: str
    attack_type: str
    description: str
    variant: ExecutionVariant
    steps: tuple[StepSpec, ...]
    edges: tuple[tuple[str, str], ...]
    total_budget: int
    acceptance: tuple[str, ...]

    @property
    def step_ids(self) -> tuple[str, ...]:
        return tuple(step.id for step in self.steps)


_BASE_CASES: dict[int, CompositeCaseSpec] = {
    7: CompositeCaseSpec(
        case_id=7,
        name="poisoned_composite_chain",
        attack_type="composite_chain_poison",
        description="A query-to-compute-to-submit chain whose middle step returns a semantic false value.",
        variant=ExecutionVariant.BASELINE,
        steps=(
            StepSpec("A", "QuerySource", "query", primary_value=25.0),
            StepSpec(
                "B",
                "ComputeValue",
                "compute",
                primary_behavior="semantic_poison",
                primary_value=0.01,
                substitute_behavior="ok",
                substitute_value=25.0,
                minimum_valid_value=1.0,
            ),
            StepSpec("C", "SubmitValue", "submit", primary_value=25.0),
        ),
        edges=(("A", "B"), ("B", "C")),
        total_budget=1,
        acceptance=(
            "B is marked as a poisoned source",
            "the poisoned label propagates to C along the dependency edge",
            "C follows the same semantic-predicate decision as the selected variant",
        ),
    ),
    8: CompositeCaseSpec(
        case_id=8,
        name="shared_dependency_budget_exhaustion",
        attack_type="composite_budget_exhaustion",
        description="A failed shared dependency has one semantically invalid substitute and two consumers.",
        variant=ExecutionVariant.BASELINE,
        steps=(
            StepSpec(
                "X",
                "SharedLookup",
                "shared_dependency",
                primary_behavior="schema_failure",
                substitute_behavior="semantic_poison",
                substitute_value=0.01,
                minimum_valid_value=1.0,
                budget=1,
            ),
            StepSpec("Y", "FirstConsumer", "consumer", primary_value=20.0),
            StepSpec("Z", "SecondConsumer", "consumer", primary_value=30.0),
        ),
        edges=(("X", "Y"), ("X", "Z")),
        total_budget=1,
        acceptance=(
            "the single recovery budget is exhausted by X",
            "X degrades explicitly after its substitute fails the semantic boundary",
            "neither consumer receives a fabricated numeric value",
        ),
    ),
    9: CompositeCaseSpec(
        case_id=9,
        name="malicious_substitution_lattice",
        attack_type="composite_a2_semantic_poison",
        description="A diamond plan combines an A2 malicious substitution request with semantic poisoning.",
        variant=ExecutionVariant.BASELINE,
        steps=(
            StepSpec("A", "RequestSource", "query", primary_value=18.0),
            StepSpec("B", "TrustedCheck", "trusted_branch", primary_value=18.0),
            StepSpec(
                "A2",
                "RiskyQuote",
                "malicious_substitution_request",
                primary_behavior="schema_failure",
                substitute_behavior="semantic_poison",
                substitute_value=0.01,
            ),
            StepSpec("C", "ChooseAndSubmit", "join", primary_value=18.0),
        ),
        edges=(("A", "B"), ("A", "A2"), ("B", "C"), ("A2", "C")),
        total_budget=1,
        acceptance=(
            "all four execution variants use the same graph and attack payload",
            "M2 records the A2 substitute provenance",
            "the schema-valid 0.01 poison remains observable at the schema-only boundary",
        ),
    ),
}


def build_case(case_id: int | str, variant: str | ExecutionVariant) -> CompositeCaseSpec:
    """Return one immutable case specification for an execution variant."""
    normalized_id = int(case_id)
    try:
        base = _BASE_CASES[normalized_id]
    except KeyError:
        raise ValueError(f"Unknown composite case: {case_id}") from None
    return replace(base, variant=ExecutionVariant(variant))


def build_cases(variant: str | ExecutionVariant) -> tuple[CompositeCaseSpec, ...]:
    """Return Cases 7, 8, and 9 in numeric order."""
    return tuple(build_case(case_id, variant) for case_id in sorted(_BASE_CASES))
