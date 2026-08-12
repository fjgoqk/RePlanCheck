# Research Roadmap

## Research Question

Can a tool-using LLM agent recover useful partial results after an untrusted
tool failure while preserving the integrity of its trusted plan and preventing
fallback values from being mistaken for validated business data?

## Threat Model

The attacker controls a third-party tool's description, implementation, and
returned content. The trusted computing base includes the abstract planning
boundary, orchestrator, schema validator, repair verifier, and experiment
recorder. The attacker must not be able to modify the trusted plan, expand the
approved tool set, expand permissions, or convert rejected output into a trusted
value.

## Milestone Gates

### M0: Verified Local Recovery

- reject output-schema violations;
- resume only through an existing trusted exception edge;
- verify plan, tools, and permissions are unchanged;
- never send rejected content to an LLM.

### M1: Trusted Outcome Semantics

- represent rejected values as `null`;
- expose per-tool result status;
- suppress misleading generated fallback output;
- append machine-readable JSONL records.

### Deterministic Replay

- freeze the abstract plan and expected tools for every case;
- run Baseline, M0, and M1 on identical fixtures;
- repeat every condition at least 30 times;
- record configuration, code reference, duration, and outcome.

### M2: Bounded Replanning

- allow only policy-approved tool substitution or local retry;
- prohibit new data flows and permission expansion;
- verify every proposed patch before execution;
- impose explicit repair and latency budgets.

### Final Evaluation

Report attack-block rate, task-completion rate, false-value rate, repair-success
rate, invariant-pass rate, mean latency, and P95 latency. Include failure cases
and planning variance rather than reporting only successful examples.
