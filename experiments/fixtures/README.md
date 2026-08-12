# Deterministic Fixtures

Fixtures will freeze the query, abstract tools, schemas, plan script, expected
tool mapping, attack type, and expected trusted outcome for each case study.

The deterministic replay runner must bypass stochastic abstract-plan generation
so every implementation variant receives the same plan.
