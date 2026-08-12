import traceback
from pathlib import Path
from time import monotonic

import click
from dotenv import load_dotenv

from ace.experiment_log import JsonlExperimentWriter
from ace.llm.embeddings import EmbeddingsEnum
from ace.llm.models import ModelsEnum
from ace.logging_config import get_logger, setup_logging
from ace.schema.handler_registry import create_development_registry
from ace.schema.outcome import ExecutionOutcome, ExecutionStatus
from ace.setup import AppConfig, setup_app

from .formatter import CLIFormatter

load_dotenv()


@click.command()
@click.option("--llm-model", default="deepseek-v4-flash", show_default=True, help="LLM model to use")
@click.option("--embedding-model", default="BAAI/bge-small-en-v1.5", show_default=True, help="Embedding model to use")
@click.option("--tool-manifest", default="tools/manifest.json", show_default=True, help="Path to tool manifest JSON")
@click.option("--temperature", default=0.0, type=float, show_default=True, help="LLM temperature")
@click.option(
    "--abstract-plan-fixture",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    default=None,
    help="Use a reviewed abstract-plan fixture instead of LLM planning",
)
@click.option(
    "--results-jsonl",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="Append trusted execution records to this JSONL file",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.option("--very-verbose", "-vv", is_flag=True, help="Enable very verbose logging")
def cli(
    llm_model,
    embedding_model,
    tool_manifest,
    temperature,
    abstract_plan_fixture,
    results_jsonl,
    verbose,
    very_verbose,
):
    """Run the ACE agent CLI."""
    # Set up comprehensive logging
    if very_verbose:
        log_level = "DEBUG"
    elif verbose:
        log_level = "INFO"
    else:
        log_level = "WARNING"

    # Configure logging to write to ace.log and optionally to console
    setup_logging(log_level=log_level, log_file="ace.log", console_output=verbose or very_verbose)

    logger = get_logger(__name__)
    logger.info(f"Starting ACE CLI with model={llm_model}, temp={temperature}, manifest={tool_manifest}")

    # Initialize CLI formatter
    formatter = CLIFormatter()
    result_writer = JsonlExperimentWriter(results_jsonl) if results_jsonl else None

    # Map string to enum (fallback to value if not found)
    llm_enum = (
        ModelsEnum(llm_model) if llm_model in ModelsEnum._value2member_map_ else ModelsEnum.GPT_4O_MINI_2024_07_18
    )
    embedding_enum = (
        EmbeddingsEnum(embedding_model)
        if embedding_model in EmbeddingsEnum._value2member_map_
        else EmbeddingsEnum.OPENAI_3_SMALL
    )
    config = AppConfig(
        llm_model=llm_enum,
        embedding_model=embedding_enum,
        tool_manifest=tool_manifest,
        temperature=temperature,
        abstract_plan_fixture=abstract_plan_fixture,
    )

    # Create development registry with CLI, logging, and debug handlers
    registry = create_development_registry()
    agent = setup_app(config, registry)
    fixture = getattr(agent.abstract_planner, "fixture", None)

    logger.info("ACE agent initialized successfully")
    logger.info(f"Agent configuration: LLM={config.llm_model.value}, Embedding={config.embedding_model.value}")

    # Display welcome banner and configuration
    formatter.print_welcome_banner()
    formatter.print_configuration(
        llm_model=config.llm_model.value,
        embedding_model=config.embedding_model.value,
        manifest=tool_manifest,
        temperature=temperature,
    )

    while True:
        try:
            query = formatter.print_query_prompt()
        except (EOFError, KeyboardInterrupt):
            formatter.print_exit_message()
            logger.info("CLI session ended by user")
            break

        logger.info(f"Processing query: {query}")
        try:
            started_at = monotonic()
            # Create a progress spinner for query processing
            with formatter.create_progress_spinner("Processing query...") as progress:
                task = progress.add_task("Processing query...", total=None)
                result = agent.run_query(query)
                progress.update(task, completed=100)

            if result_writer and isinstance(result, ExecutionOutcome):
                record = result_writer.append(
                    query=query,
                    llm_model=config.llm_model.value,
                    embedding_model=config.embedding_model.value,
                    tool_manifest=tool_manifest,
                    temperature=temperature,
                    duration_ms=round((monotonic() - started_at) * 1000),
                    outcome=result,
                    plan_fixture=str(abstract_plan_fixture) if abstract_plan_fixture else None,
                    plan_digest=fixture.plan_digest if fixture else None,
                    expected_tools=fixture.expected_tools if fixture else None,
                )
                logger.info(f"Appended experiment record {record.run_id} to {results_jsonl}")

            if isinstance(result, ExecutionOutcome) and result.status is not ExecutionStatus.SUCCESS:
                formatter.print_warning(f"Query completed with status: {result.status.value}")
            else:
                formatter.print_success("Query completed successfully")
            logger.info(f"Query completed with result type {type(result).__name__}")
            logger.debug(f"Query result type: {type(result).__name__}")
            if hasattr(agent, "output_log") and agent.output_log:
                logger.debug(f"Most recent output: {agent.output_log[-1]}")
        except Exception as e:
            error_msg = traceback.format_exc()
            logger.error(f"Query failed with internal error: {e}", exc_info=True)
            formatter.print_error(
                f"Query failed with an internal runtime error:\n{error_msg}\n\nPlease check the logs for details."
            )
