import importlib
import json
from types import SimpleNamespace

import pytest

replay = importlib.import_module("experiments.stages.03_deterministic_replay.run")


def _record(**overrides):
    record = {
        "schema_version": "1.3",
        "variant": "baseline",
        "git_commit": "commit",
        "plan_digest": "plan",
        "llm_model": "deepseek-v4-flash",
        "embedding_model": "BAAI/bge-small-en-v1.5",
        "temperature": 0.0,
        "recovery_manifest": None,
        "approved_substitutions": {},
        "expected_tools": ["QuickRide", "MetroHail"],
        "case_id": "case_1",
        "trial": 1,
    }
    record.update(overrides)
    return record


def test_resume_loads_only_compatible_completed_trials(tmp_path, monkeypatch):
    output = tmp_path / "runs.jsonl"
    output.write_text(json.dumps(_record()) + "\n", encoding="utf-8")
    fixture = SimpleNamespace(plan_digest="plan", expected_tools=["QuickRide", "MetroHail"])
    monkeypatch.setattr(replay, "current_git_commit", lambda: "commit")

    completed = replay.load_completed_trials(
        output,
        case_ids=["1", "2", "3"],
        trials=30,
        variant="baseline",
        fixture=fixture,
        llm_model="deepseek-v4-flash",
        embedding_model="BAAI/bge-small-en-v1.5",
        temperature=0.0,
    )

    assert completed == {("case_1", 1)}


def test_resume_rejects_a_different_git_commit(tmp_path, monkeypatch):
    output = tmp_path / "runs.jsonl"
    output.write_text(json.dumps(_record()) + "\n", encoding="utf-8")
    fixture = SimpleNamespace(plan_digest="plan", expected_tools=["QuickRide", "MetroHail"])
    monkeypatch.setattr(replay, "current_git_commit", lambda: "new-commit")

    with pytest.raises(ValueError, match="git_commit"):
        replay.load_completed_trials(
            output,
            case_ids=["1"],
            trials=30,
            variant="baseline",
            fixture=fixture,
            llm_model="deepseek-v4-flash",
            embedding_model="BAAI/bge-small-en-v1.5",
            temperature=0.0,
        )
