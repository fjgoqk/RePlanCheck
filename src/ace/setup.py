from ace.agent import AceAgent
from ace.analysis import configure_analyzer
from ace.llm.base import create_llm
from ace.llm.embeddings import EmbeddingsEnum, create_embedding
from ace.llm.models import ModelsEnum
from ace.plan.abstract import AbstractPlanner
from ace.plan.concrete import InfoFlowPlanner
from ace.plan.fixture import FixtureAbstractPlanner, PlanFixture
from ace.schema.events import AgentEventHandler
from ace.schema.handler_registry import HandlerRegistry
from ace.schema.outcome import ExecutionVariant
from ace.tools.manager import ToolManager


class AppConfig:
    def __init__(
        self,
        llm_model=ModelsEnum.DEEPSEEK_V4_FLASH,
        embedding_model=EmbeddingsEnum.BGE_SMALL_EN_V1_5,
        tool_manifest="tools/manifest.json",
        temperature=0.0,
        abstract_plan_fixture=None,
        execution_variant=ExecutionVariant.M1,
        recovery_manifest=None,
        recovery_substitutions=None,
    ):
        self.llm_model = llm_model
        self.embedding_model = embedding_model
        self.tool_manifest = tool_manifest
        self.temperature = temperature
        self.abstract_plan_fixture = abstract_plan_fixture
        self.execution_variant = ExecutionVariant(execution_variant)
        self.recovery_manifest = recovery_manifest
        self.recovery_substitutions = recovery_substitutions or {}


def setup_app(config: AppConfig, event_registry: HandlerRegistry | AgentEventHandler | None = None) -> AceAgent:
    base_llm = create_llm(config.llm_model, temperature=config.temperature)
    embedding_model = create_embedding(config.embedding_model)
    tool_manager = ToolManager.from_manifest(config.tool_manifest)
    recovery_catalog = {}
    if config.recovery_manifest:
        recovery_manager = ToolManager.from_manifest(config.recovery_manifest)
        recovery_catalog = {tool.name: tool for tool in recovery_manager.tools}
    analyzer = configure_analyzer()
    if config.abstract_plan_fixture:
        fixture = PlanFixture.load(config.abstract_plan_fixture)
        abstract_planner = FixtureAbstractPlanner(fixture=fixture, analyzer=analyzer)
    else:
        abstract_planner = AbstractPlanner(base_llm=base_llm, analyzer=analyzer)
    concrete_planner = InfoFlowPlanner(
        tool_manager=tool_manager,
        base_llm=base_llm,
        embedding_model=embedding_model,
        analyzer=analyzer,
        filter_threshold=0.1,
    )
    return AceAgent(
        abstract_planner=abstract_planner,
        concrete_planner=concrete_planner,
        event_registry=event_registry,
        execution_variant=config.execution_variant,
        recovery_catalog=recovery_catalog,
        recovery_substitutions=config.recovery_substitutions,
    )
