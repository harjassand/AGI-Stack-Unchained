# Documentation Hub

Project specifications, audit reports, evidence artifacts, and operational notes.

## What Lives Here

- Product and protocol specifications (`*_spec.md`).
- Task plans (`*_tasks.yaml`).
- Probe and runtime reports (`*_report_YYYY-MM-DD.md`).
- Metrics and evidence snapshots (`*.json`, `*.txt`).
- Domain-specific handoff material (`eudrs_u/`).

## Suggested Taxonomy

- `*_spec.md`: Normative behavior and architecture.
- `*_tasks.yaml`: Implementation checklist and execution plan.
- `*_report_YYYY-MM-DD.md`: Human-readable run/audit findings.
- `*_YYYY-MM-DD.json`: Structured output for tooling and dashboards.

## Naming Guidelines

1. Include explicit version markers where contracts are versioned.
2. Include a date suffix for time-scoped artifacts.
3. Prefer descriptive prefixes (`phase4_`, `apfsc_`, `epoch_`) for discoverability.

## Subdirectories

- `eudrs_u/`: EUDRS-U scientist handoff and spec-outline documentation.

## Maintenance

- Do not store generated binaries in this directory.
- If a document changes behavior contracts, link it from the relevant module README.
