# Orchestrator RL Data

Staging area for orchestrator reinforcement-learning datasets and manifests.

## Current Layout

- `datasets/manifests/`: Placeholder root for RL dataset manifest artifacts.

## Intended Lifecycle

1. Collect transition or rollout events.
2. Build deterministic dataset manifests.
3. Promote datasets through verifier-compatible contracts.

## Rules

- Use hash-addressed manifest naming once artifacts are introduced.
- Keep this directory as data-only state; executable logic belongs in source modules.
