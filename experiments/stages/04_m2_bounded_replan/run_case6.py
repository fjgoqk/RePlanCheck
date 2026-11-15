import argparse
import json
from pathlib import Path
from time import monotonic

from dotenv import load_dotenv

from ace.execute.orchestrator import ExecutionAbortedError
from ace.experiment_log import EXPERIMENT_SCHEMA_VERSION, JsonlExperimentWriter, current_git_commit
from ace.llm.embeddings import EmbeddingsEnum
from ace.llm.models import ModelsEnum
from ace.plan.fixture import PlanFixture
from ace.schema.outcome import ExecutionVariant
from ace.setup import AppConfig, setup_app

CASE_ATTACKS = {
    "1": "planner_manipulation",
    "2": "execution_interruption",
    "3": "execution_result_hijacking",
    "4": "semantic_fake_value",
    "5": "substitute_tool_failure",
    "6": "composed_semantic_poison",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay one execution policy with a deterministic abstract plan")
    parser.add_argument("--case", choices=["1", "2", "3", "4", "5", "6", "all"], default="all")
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument(
        "--variant",
        choices=[variant.value for variant in ExecutionVariant],
        default=ExecutionVariant.M1.value,
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path("experiments/fixtures/case_studies/fare_comparison.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
    )
    output_mode = parser.add_mutually_exclusive_group()
    output_mode.add_argument("--overwrite", action="store_true")
    output_mode.add_argument("--resume", action="store_true")
    parser.add_argument("--llm-model", default=ModelsEnum.DEEPSEEK_V4_FLASH.value)
    parser.add_argument("--embedding-model", default=EmbeddingsEnum.BGE_SMALL_EN_V1_5.value)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--recovery-manifest", type=Path)
    parser.add_argument(
        "--substitution",
        action="append",
        default=[],
        metavar="ABSTRACT_TOOL=CONCRETE_TOOL",
    )
    args = parser.parse_args()
    if args.trials < 1:
        parser.error("--trials must be at least 1")
    if args.output is None:
        stage = "stage04" if args.variant == ExecutionVariant.M2.value else "stage03"
        args.output = Path(f"results/raw/{stage}/{args.variant}-deterministic-replay.jsonl")
    args.recovery_substitutions = parse_substitutions(parser, args.substitution)
    if args.variant == ExecutionVariant.M2.value and not (args.recovery_manifest and args.recovery_substitutions):
        parser.error("m2 requires --recovery-manifest and at least one --substitution")
    if args.variant != ExecutionVariant.M2.value and (args.recovery_manifest or args.recovery_substitutions):
        parser.error("recovery substitutions are only valid for m2")
    if args.output.exists() and not (args.overwrite or args.resume):
        parser.error(f"output already exists: {args.output}; use --resume, --overwrite, or choose another path")
    return args


def parse_substitutions(parser: argparse.ArgumentParser, values: list[str]) -> dict[str, list[str]]:
    substitutions: dict[str, list[str]] = {}
    for value in values:
        abstract_tool, separator, concrete_tool = value.partition("=")
        if not separator or not abstract_tool or not concrete_tool:
            parser.error(f"invalid --substitution value: {value!r}")
        substitutions.setdefault(abstract_tool, []).append(concrete_tool)
    return substitutions


def load_completed_trials(
    path: Path,
    *,
    case_ids: list[str],
    trials: int,
    variant: str,
    fixture: PlanFixture,
    llm_model: str,
    embedding_model: str,
    temperature: float,
    recovery_manifest: str | None = None,
    approved_substitutions: dict[str, list[str]] | None = None,
) -> set[tuple[str, int]]:
    if not path.exists():
        return set()

    expected_commit = current_git_commit()
    selected_cases = {f"case_{case_id}" for case_id in case_ids}
    completed: set[tuple[str, int]] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL record at line {line_number}") from exc

        expected_fields = {
            "schema_version": EXPERIMENT_SCHEMA_VERSION,
            "variant": variant,
            "git_commit": expected_commit,
            "plan_digest": fixture.plan_digest,
            "llm_model": llm_model,
            "embedding_model": embedding_model,
            "temperature": temperature,
            "recovery_manifest": recovery_manifest,
            "approved_substitutions": approved_substitutions or {},
        }
        for field, expected in expected_fields.items():
            if record.get(field) != expected:
                raise ValueError(
                    f"Cannot resume: line {line_number} has {field}={record.get(field)!r}, expected {expected!r}"
                )
        if record.get("expected_tools") != fixture.expected_tools:
            raise ValueError(f"Cannot resume: expected tool set differs at line {line_number}")

        case_id = record.get("case_id")
        trial = record.get("trial")
        if case_id not in selected_cases:
            raise ValueError(f"Cannot resume: unexpected case {case_id!r} at line {line_number}")
        if not isinstance(trial, int) or not 1 <= trial <= trials:
            raise ValueError(f"Cannot resume: invalid trial {trial!r} at line {line_number}")

        key = (case_id, trial)
        if key in completed:
            raise ValueError(f"Cannot resume: duplicate {case_id} trial {trial}")
        completed.add(key)
    return completed


def main() -> None:
    load_dotenv()
    args = parse_args()
    if args.overwrite and args.output.exists():
        args.output.unlink()
    fixture = PlanFixture.load(args.fixture)
    case_ids = list(CASE_ATTACKS) if args.case == "all" else [args.case]
    completed = (
        load_completed_trials(
            args.output,
            case_ids=case_ids,
            trials=args.trials,
            variant=args.variant,
            fixture=fixture,
            llm_model=args.llm_model,
            embedding_model=args.embedding_model,
            temperature=args.temperature,
            recovery_manifest=str(args.recovery_manifest) if args.recovery_manifest else None,
            approved_substitutions=args.recovery_substitutions,
        )
        if args.resume
        else set()
    )
    writer = JsonlExperimentWriter(args.output)
    if completed:
        print(json.dumps({"resume": True, "completed": len(completed)}, separators=(",", ":")))

    for case_id in case_ids:
        manifest = Path(f"benchmarks/case_studies/case_{case_id}/tools/manifest.json")
        for trial in range(1, args.trials + 1):
            if (f"case_{case_id}", trial) in completed:
                continue
            config = AppConfig(
                llm_model=ModelsEnum(args.llm_model),
                embedding_model=EmbeddingsEnum(args.embedding_model),
                tool_manifest=str(manifest),
                temperature=args.temperature,
                abstract_plan_fixture=str(args.fixture),
                execution_variant=ExecutionVariant(args.variant),
                recovery_manifest=str(args.recovery_manifest) if args.recovery_manifest else None,
                recovery_substitutions=args.recovery_substitutions,
            )
            agent = setup_app(config)
            started_at = monotonic()
            try:
                outcome = agent.run_query(fixture.query)
            except ExecutionAbortedError as exc:
                outcome = exc.outcome
            duration_ms = round((monotonic() - started_at) * 1000)
            record = writer.append(
                query=fixture.query,
                llm_model=args.llm_model,
                embedding_model=args.embedding_model,
                tool_manifest=str(manifest),
                temperature=args.temperature,
                duration_ms=duration_ms,
                outcome=outcome,
                variant=config.execution_variant.value,
                case_id=f"case_{case_id}",
                trial=trial,
                attack_type=CASE_ATTACKS[case_id],
                plan_fixture=str(args.fixture),
                plan_digest=fixture.plan_digest,
                expected_tools=fixture.expected_tools,
                mapped_tools=sorted(set(agent.last_tool_mapping.values())),
                recovery_manifest=str(args.recovery_manifest) if args.recovery_manifest else None,
                approved_substitutions=agent.last_approved_substitutions,
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
