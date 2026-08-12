# Stage 01: M0 Verified Local Recovery

- Status: complete
- Objective: reject invalid output and resume through the existing trusted
  exception path.
- Security gate: unchanged plan digest, approved tool set, and permission set;
  at most one repair per tool.
- Known limitation: the generated plan may create a numeric fallback such as
  `0.0`, which is not a validated business value.
