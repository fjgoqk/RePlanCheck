# WP2 Composite Experiment Overview

Each row summarizes 30 deterministic runs.

| Variant | Case | Completion | Retention | False value | Budget used | Exhausted | Degraded | Substituted | Substitute sources | Poisoned sources |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | case_7 | 0.0% | 0.0% | 0.0% | 0 | 0 | 0 | 0 | 0 | 60 |
| baseline | case_8 | 0.0% | 0.0% | 0.0% | 0 | 0 | 0 | 0 | 0 | 0 |
| baseline | case_9 | 0.0% | 0.0% | 0.0% | 0 | 0 | 0 | 0 | 0 | 0 |
| m0 | case_7 | 0.0% | 100.0% | 100.0% | 0 | 0 | 0 | 0 | 0 | 60 |
| m0 | case_8 | 0.0% | 100.0% | 100.0% | 0 | 0 | 0 | 0 | 0 | 0 |
| m0 | case_9 | 0.0% | 100.0% | 100.0% | 0 | 0 | 0 | 0 | 0 | 0 |
| m1 | case_7 | 0.0% | 100.0% | 100.0% | 0 | 0 | 30 | 0 | 0 | 60 |
| m1 | case_8 | 0.0% | 100.0% | 0.0% | 0 | 0 | 30 | 0 | 0 | 0 |
| m1 | case_9 | 0.0% | 100.0% | 0.0% | 0 | 0 | 30 | 0 | 0 | 0 |
| m2 | case_7 | 100.0% | 100.0% | 0.0% | 30 | 30 | 0 | 30 | 60 | 60 |
| m2 | case_8 | 0.0% | 100.0% | 0.0% | 30 | 30 | 30 | 30 | 90 | 0 |
| m2 | case_9 | 100.0% | 100.0% | 100.0% | 30 | 30 | 0 | 30 | 60 | 0 |

## WP1 single-point comparison framework

| Comparison question | WP1 field | WP2 field | Interpretation |
| --- | --- | --- | --- |
| Did the whole plan finish? | `full_task_completion_rate` | `full_task_completion_rate` | Direct rate comparison is valid. |
| Was a usable partial result retained? | `useful_result_retention_rate` | `useful_result_retention_rate` | Both count `success` and `partial_success`. |
| Did an unverified value escape? | `false_value_rate` | `false_value_propagation_rate` | WP2 additionally checks downstream event and provenance evidence. |
| Was recovery bounded? | Repair evidence | Budget consumed and exhausted counts | Compare policy behavior; WP1 summaries do not expose the same budget counters. |
| Can substituted or poisoned inputs be traced? | Repair records | Source-marker counts | WP2 adds per-step provenance, so this is not a direct numeric comparison. |

A final WP1 versus WP2 claim should compare matched variants and attack semantics.
Cases 7–9 add dependencies, shared-budget exhaustion, and a join, so their raw rates
should not be pooled with single-point cases without identifying the case mix.
