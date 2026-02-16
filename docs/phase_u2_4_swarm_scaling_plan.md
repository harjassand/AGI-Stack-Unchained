# Phase U-2.4 Swarm Scaling Plan (Scaffold)

## Scope

This document is a placeholder for Phase U-2.4 design work. It introduces no runtime changes and no new trust surfaces.

## Distributed Run Orchestration via Swarm Runners

- Define deterministic swarm runner roles (coordinator, shard worker, verifier worker, aggregator).
- Keep campaign dispatch and goal synthesis authority unchanged in the omega coordinator.
- Use receipt-addressed handoff artifacts between swarm workers to preserve replayability.
- Pin shard assignment and merge order with stable sorting and deterministic tie-breakers.
- Treat worker outputs as untrusted until verified by existing verifier modules.

## Failure Analysis from Run Artifacts (No New Trust)

- Build automatic failure summaries only from existing run artifacts:
  - verifier outputs
  - dispatch receipts
  - benchmark summaries
  - promotion/refutation receipts
- Emit analysis-only summaries as derived reports (no promotion authority).
- Preserve deterministic summaries by canonicalizing input sets and sorting by stable keys.
- Include explicit failure buckets:
  - nondeterminism/canonicalization errors
  - verifier schema/hash failures
  - budget/cooldown gating failures
  - activation/promotion failures

## Open Design Threads

- Shard sizing policy vs verifier throughput limits.
- Retry policy for transient worker failures without reordering deterministic outcomes.
- Evidence index format for cross-run failure trend analysis.
