# Legacy planner tests

The 19 skipped tests in this directory cover planner and schema behavior from July 2025. They predate RePlanCheck and no longer describe the active implementation.

The schema cases were replaced by the current plan grammar and validation semantics. The planner cases were replaced by structured-output LLM integration, the compatibility-chain setup, and FAISS-backed tool filtering through the refactored `faiss_store` field. The least-privilege case also depends on that newer tool-selection path.

These tests remain in place as historical documentation. Marking them with explicit skip reasons keeps their original assertions available for reference without presenting obsolete behavior as a current requirement. They were not deleted because they still record earlier design assumptions and may help explain older planner behavior.

The active suite has 106 passing tests. With these legacy cases marked, the expected result is 106 passed, 19 skipped, and 0 failed.
