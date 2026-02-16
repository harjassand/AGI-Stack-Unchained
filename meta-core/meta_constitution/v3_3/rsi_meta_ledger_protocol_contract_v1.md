# RSI Meta-Ledger Protocol Contract v1 (v3.3)

This contract defines the v3.3 holographic meta-ledger protocol for swarm runs.

## Scope
- Meta exchange lives at `@ROOT/meta_exchange/`.
- Meta updates, blocks, state, and policy are content-addressed and immutable.
- Meta policy takes effect at epoch boundaries only (no mid-epoch switching).

## Determinism
- All canonical JSON uses GCJ-1 canonicalization.
- All hashes are `sha256` of canonical JSON (or raw bytes for blobs).
- Updates are incorporated into the block for their publish epoch only.

## Required invariants
- Updates and blocks must match root run ID and ICORE ID.
- Update IDs / hashes must match canonical content and filenames.
- Updates must reference a VALID `RESULT_VERIFY` event.
- Meta policy changes are restricted to allowlisted keys only.

## Consensus (HOLO_CONSENSUS_V1)
- For each epoch `e` in `[0..max_epochs-1]`, a unique block `B_e` is derived.
- Inputs are: prior block, all updates published at `e`, and deterministic merge rules.
- Accepted updates are applied in ascending `update_id` order.

## Policy merge rules
- `bridge.subscriptions_add`: set-union; stored sorted unique.
- `task.priority_boost`: per-topic max; stored sorted by topic.

## Bounded latency
- An update published at epoch `e` must be included in `B_e` (accepted or rejected).
- It must not first appear in any `B_{e+k}` for `k>0`.

## Receipts
- Each node declares meta heads with `META_HEAD_DECLARE`.
- The root emits `meta_ledger_report_v1.json` for diagnostics.
