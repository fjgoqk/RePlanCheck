# RePlanCheck

**Verified and bounded recovery for tool-using LLM agents.**

RePlanCheck studies how an agent can continue useful work after an untrusted
tool fails validation without allowing that tool to alter the trusted plan,
tool set, permission set, or final business result.

The project extends the
[ACE architecture](https://github.com/escottrose01/ace-llm) with verified local
recovery, structured execution outcomes, and reproducible failure-recovery
experiments.

## Current Results

The current `replancheck-m1` milestone provides:

- local rejection of tool outputs that fail schema validation;
- repair verification over plan, tool-set, and permission-set invariants;
- trusted `ExecutionOutcome` records with per-tool `success` or `rejected`
  states;
- `null` for unavailable values instead of misleading numeric fallbacks;
- append-only JSONL experiment records without raw attack payloads;
- DeepSeek V4 Flash support and local BGE embeddings.

The Case 2 and Case 3 demonstrations reject the malicious QuickRide result,
retain the validated MetroHail fare, and return `partial_success`.

## Research Stages

| Stage | Milestone | Status | Code reference |
| --- | --- | --- | --- |
| 00 | ACE baseline reproduction | Complete | `e88f6dc` |
| 01 | M0 verified local recovery | Complete | included in M1 checkpoint |
| 02 | M1 structured outcomes and JSONL logging | Complete | `replancheck-m1` |
| 03 | Deterministic plan replay | Next | planned |
| 04 | M2 bounded tool substitution/replanning | Planned | planned |
| 05 | Final comparative evaluation | Planned | planned |

See [`experiments/README.md`](experiments/README.md) for the experiment layout
and [`docs/research-roadmap.md`](docs/research-roadmap.md) for milestone gates.

## Repository Layout

```text
src/                  RePlanCheck and inherited ACE implementation
tests/                Unit, provider, recovery, and outcome tests
benchmarks/           ACE benchmark integrations and case-study tools
experiments/          Stage definitions, deterministic fixtures, and analysis
results/              Curated summaries and processed research outputs
docs/                 Architecture, roadmap, and reproduction documentation
paper/                Manuscript, figure, and submission workspace
scripts/              Project-level automation entry points
```

Source code is not copied between stages. Git tags freeze implementation
checkpoints, while `experiments/stages/` stores each stage's protocol and
expected artifacts.

## Setup

Requirements:

- Python 3.12
- Docker
- a DeepSeek API key for the default model

```bash
git clone https://github.com/fjgoqk/RePlanCheck.git
cd RePlanCheck
uv sync --python 3.12
```

Create a local `.env` file. It is ignored by Git.

```bash
DEEPSEEK_API_KEY=your_key_here
```

Build the execution images:

```bash
cd src/ace/execute
docker build -t worker-image -f Dockerfile.worker .
docker build -t tool-runner-image -f Dockerfile.tool .
cd ../../..
```

## Run The Case Studies

```bash
./benchmarks/case_studies/run.sh
```

Defaults:

- planner and compatibility model: `deepseek-v4-flash`;
- embedding model: local `BAAI/bge-small-en-v1.5`;
- execution timeout: 300 seconds;
- structured records: `results/replancheck_m1/case_studies/runs.jsonl`.

Run the focused regression suite:

```bash
PYTHONPATH=src .venv/bin/pytest -q \
  tests/test_outcome.py \
  tests/test_recovery.py \
  tests/test_plan_orchestrator.py \
  tests/test_ace_agent.py \
  tests/test_embeddings.py \
  tests/test_llm_providers.py \
  tests/test_concrete_planner.py
```

## Security And Data Handling

- Never commit `.env`, API keys, credentials, or private datasets.
- Raw rejected tool output is represented by a SHA-256 digest in audit records.
- Raw JSONL records and logs are ignored until they are reviewed and reduced to
  curated aggregate results.
- A repair is accepted only when the trusted plan digest, approved tool set, and
  permission set remain unchanged.

## Upstream ACE

RePlanCheck is research derived from **ACE: A Security Architecture for
LLM-Integrated App Systems** by Evan Li, Tushin Mallick, Evan Rose, William
Robertson, Alina Oprea, and Cristina Nita-Rotaru. The upstream repository and
paper should remain cited in any publication or public release of this work.

```bibtex
@misc{li2025ace,
  title={ACE: A Security Architecture for LLM-Integrated App Systems},
  author={Evan Li and Tushin Mallick and Evan Rose and William Robertson and Alina Oprea and Cristina Nita-Rotaru},
  year={2025},
  eprint={2504.20984},
  archivePrefix={arXiv},
  primaryClass={cs.CR},
  url={https://arxiv.org/abs/2504.20984}
}
```

## Publication Status

RePlanCheck is an active research prototype. Results should be treated as
preliminary until deterministic replay and repeated comparative evaluation are
complete.
