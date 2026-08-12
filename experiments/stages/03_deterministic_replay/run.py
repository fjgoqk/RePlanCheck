import argparse
import json
from pathlib import Path
from time import monotonic

from dotenv import load_dotenv

from ace.experiment_log import JsonlExperimentWriter
from ace.llm.embeddings import EmbeddingsEnum
from ace.llm.models import ModelsEnum
from ace.plan.fixture import PlanFixture
from ace.setup import AppConfig, setup_app

CASE_ATTACKS = {
    "1": "planner_manipulation",
    "2": "execution_interruption",
    "3": "execution_result_hijacking",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run M1 with a deterministic abstract-plan fixture")
    parser.add_argument("--case", choices=["1", "2", "3", "all"], default="all")
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path("experiments/fixtures/case_studies/fare_comparison.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/raw/stage03/m1-deterministic-replay.jsonl"),
    )
    parser.add_argument("--llm-model", default=ModelsEnum.DEEPSEEK_V4_FLASH.value)
    parser.add_argument("--embedding-model", default=EmbeddingsEnum.BGE_SMALL_EN_V1_5.value)
    parser.add_argument("--temperature", type=float, default=0.0)
    args = parser.parse_args()
    if args.trials < 1:
        parser.error("--trials must be at least 1")
    return args


def main() -> None:
    load_dotenv()
    args = parse_args()
    fixture = PlanFixture.load(args.fixture)
    writer = JsonlExperimentWriter(args.output)
    case_ids = list(CASE_ATTACKS) if args.case == "all" else [args.case]

    for case_id in case_ids:
        manifest = Path(f"benchmarks/case_studies/case_{case_id}/tools/manifest.json")
        for trial in range(1, args.trials + 1):
            config = AppConfig(
                llm_model=ModelsEnum(args.llm_model),
                embedding_model=EmbeddingsEnum(args.embedding_model),
                tool_manifest=str(manifest),
                temperature=args.temperature,
                abstract_plan_fixture=str(args.fixture),
            )
            agent = setup_app(config)
            started_at = monotonic()
            outcome = agent.run_query(fixture.query)
            duration_ms = round((monotonic() - started_at) * 1000)
            record = writer.append(
                query=fixture.query,
                llm_model=args.llm_model,
                embedding_model=args.embedding_model,
                tool_manifest=str(manifest),
                temperature=args.temperature,
                duration_ms=duration_ms,
                outcome=outcome,
                variant="m1",
                case_id=f"case_{case_id}",
                trial=trial,
                attack_type=CASE_ATTACKS[case_id],
                plan_fixture=str(args.fixture),
                plan_digest=fixture.plan_digest,
                expected_tools=fixture.expected_tools,
            )
            print(
                json.dumps(
                    {
                        "run_id": record.run_id,
                        "case_id": record.case_id,
                        "trial": record.trial,
                        "status": outcome.status.value,
                        "duration_ms": duration_ms,
                    },
                    separators=(",", ":"),
                )
            )


if __name__ == "__main__":
    main()
