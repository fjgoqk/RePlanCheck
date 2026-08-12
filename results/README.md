# Results

- `case_studies_summary.md`: reviewed narrative summary.
- `raw/`: local-only JSONL and logs.
- `processed/`: reviewed aggregate CSV or JSON files suitable for version control.
- `figures/`: generated paper figures.

The final same-commit four-variant comparison is under
`processed/stage05/512de4c/`; its paper figures are under
`figures/stage05/512de4c/`.

Unreviewed JSONL files and logs are ignored by Git. Before publishing an
aggregate, verify that it contains no credentials, private queries, or raw
attack payloads.
