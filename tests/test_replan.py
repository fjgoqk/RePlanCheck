import pytest
from pydantic import BaseModel

from src.ace.plan.concrete import SchemaAdaptedTool
from src.ace.replan import SubstitutionApprovalError, build_approved_substitutions
from src.ace.schema.concrete import ConcreteToolBase
from src.ace.schema.permissions import Permission


class RawArgs(BaseModel):
    start_point: str
    end_point: str


class RawOutput(BaseModel):
    result: float


class AbstractArgs(BaseModel):
    pickup: str
    destination: str


class AbstractOutput(BaseModel):
    fare: float


class StubTool(ConcreteToolBase):
    def generate_source(self) -> str:
        return "def main(start_point, end_point):\n    return {'result': 49.2}\n"


def _raw_tool(name: str, permissions: set[Permission] | None = None) -> StubTool:
    return StubTool(
        name=name,
        provider="test",
        description="fare",
        clearances={"public"},
        permissions=permissions or set(),
        args_schema=RawArgs,
        output_schema=RawOutput,
    )


def _selected_tool() -> SchemaAdaptedTool:
    raw = _raw_tool("QuickRide")
    return SchemaAdaptedTool(
        name=raw.name,
        provider=raw.provider,
        description=raw.description,
        clearances=raw.clearances,
        permissions=raw.permissions,
        args_schema=AbstractArgs,
        output_schema=AbstractOutput,
        wrapped_tool=raw,
        input_mapping_source=(
            "def input_mapping(pickup, destination): return {'start_point': pickup, 'end_point': destination}"
        ),
        output_mapping_source="def output_mapping(result): return {'fare': result['result']}",
    )


def test_preapproved_substitution_reuses_verified_schema_adapter():
    approved = build_approved_substitutions(
        selected_tools={"QuickRideFareEstimate": _selected_tool()},
        recovery_catalog={"QuickRideVerified": _raw_tool("QuickRideVerified")},
        requested={"QuickRideFareEstimate": ["QuickRideVerified"]},
    )

    replacement = approved["QuickRideFareEstimate"][0]
    assert replacement.name == "QuickRideVerified"
    assert isinstance(replacement, SchemaAdaptedTool)
    assert replacement.args_schema is AbstractArgs
    assert replacement.output_schema is AbstractOutput


def test_preapproved_substitution_rejects_permission_increase():
    with pytest.raises(SubstitutionApprovalError, match="increases permissions"):
        build_approved_substitutions(
            selected_tools={"QuickRideFareEstimate": _selected_tool()},
            recovery_catalog={
                "QuickRideVerified": _raw_tool("QuickRideVerified", {Permission.NETWORK}),
            },
            requested={"QuickRideFareEstimate": ["QuickRideVerified"]},
        )
