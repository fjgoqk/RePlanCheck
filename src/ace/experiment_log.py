import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .schema.outcome import ExecutionOutcome


class ExperimentRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    query: str
    query_sha256: str
    llm_model: str
    embedding_model: str
    tool_manifest: str
    temperature: float
    duration_ms: int
    git_commit: str | None
    outcome: ExecutionOutcome


class JsonlExperimentWriter:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(
        self,
        *,
        query: str,
        llm_model: str,
        embedding_model: str,
        tool_manifest: str,
        temperature: float,
        duration_ms: int,
        outcome: ExecutionOutcome,
    ) -> ExperimentRecord:
        record = ExperimentRecord(
            query=query,
            query_sha256=hashlib.sha256(query.encode()).hexdigest(),
            llm_model=llm_model,
            embedding_model=embedding_model,
            tool_manifest=tool_manifest,
            temperature=temperature,
            duration_ms=duration_ms,
            git_commit=_current_git_commit(),
            outcome=outcome,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(record.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")))
            output.write("\n")
        return record


def _current_git_commit() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip() or None
