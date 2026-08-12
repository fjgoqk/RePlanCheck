# Deterministic Fixtures

Fixtures will freeze the query, abstract tools, schemas, plan script, expected
tool mapping, attack type, and expected trusted outcome for each case study.

The deterministic replay runner must bypass stochastic abstract-plan generation
so every implementation variant receives the same plan.

`case_studies/fare_comparison.json` is the first fixture. It fixes two abstract
fare tools, their schemas, the complete Python plan, and the expected concrete
tools used by ACE Case 1, Case 2, and Case 3.
