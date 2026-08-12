# Stage 02: M1 Structured Outcomes

- Status: complete
- Code reference: `replancheck-m1`
- Objective: separate trusted tool results from generated-plan fallback values.
- Outcome: rejected values use `status=rejected, value=null`; partial runs use
  `status=partial_success, final_output=null`.
- Records: JSONL configuration, duration, code reference, failures, and repairs.
- Verification: focused regression suite passes with 28 tests.
