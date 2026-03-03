# Orchestrator Bandit State

Reserved runtime state root for orchestration bandit policies.

## Current Layout

- `state/`: Bandit state workspace (currently scaffolded with `.gitkeep`).

## Intended Use

- Store bandit model checkpoints, selection statistics, and rollout metadata.
- Keep generated state deterministic and schema-tagged when formalized.

## Guidance

- Do not commit ad-hoc or unversioned formats here once bandit artifacts are introduced.
- Add a schema and promotion path before introducing durable decision logic.
