import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from ..schema.abstract import AbstractPlan, AbstractTool, ToolSchema
from .abstract import create_pydantic_schema


class PlanFixture(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    fixture_id: str
    query: str
    tools: list[ToolSchema]
    script: str
    expected_tools: list[str]

    @classmethod
    def load(cls, path: str | Path) -> "PlanFixture":
        fixture_path = Path(path)
        return cls.model_validate(json.loads(fixture_path.read_text(encoding="utf-8")))

    @property
    def plan_digest(self) -> str:
        return hashlib.sha256(self.script.encode()).hexdigest()

    def to_abstract_plan(self) -> AbstractPlan:
        abstract_tools = []
        for tool in self.tools:
            args_schema = create_pydantic_schema([parameter.model_dump() for parameter in tool.inputs])
            output_schema = create_pydantic_schema([parameter.model_dump() for parameter in tool.outputs])
            abstract_tools.append(
                AbstractTool(
                    name=tool.name,
                    description=tool.description,
                    args_schema=args_schema,
                    output_schema=output_schema,
                )
            )
        return AbstractPlan(script=self.script, abs_tools=abstract_tools)


class FixtureAbstractPlanner:
    """Returns a reviewed abstract plan instead of invoking an LLM."""

    def __init__(self, fixture: PlanFixture, analyzer: Any | None = None) -> None:
        self.fixture = fixture
        self.analyzer = analyzer

    def generate_abstract_plan(self, query: str) -> AbstractPlan:
        if query.strip() != self.fixture.query.strip():
            raise ValueError(
                f"Query does not match deterministic fixture {self.fixture.fixture_id}; "
                "use the exact fixture query"
            )

        plan = self.fixture.to_abstract_plan()
        if self.analyzer:
            self.analyzer.analyze_post_abstract_tools(plan.abs_tools)
            self.analyzer.analyze_post_abstract_plan(plan)
        return plan
