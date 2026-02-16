# RSI Lateral Bridge Protocol Contract v1

This contract specifies the v3.2 lateral bridge protocol requirements:

- Immutable core locking: the v3.2 lock must include v3.2 schemas, verifier logic, swarm ledger hashing logic, and coordinator/worker code that governs spawn/join ordering, path rules, and bridge publish/import behavior.
- Attestation required: every swarm node (root + descendants) must include a VALID immutable core receipt at the node root, plus agent receipts.
- Deterministic ledgering: swarm ledger and barrier ledger entries are hashed via GCJ-1 canonical JSON and `sha256`.
- Event ref-hash rules: `event_ref_hash` is used for cross-ledger references; cycle-breaking event types compute `event_ref_hash` with excluded payload fields.
- Authority tree + knowledge graph: authority edges remain hierarchical (spawn/join), while bridge offers/imports form a verified directed knowledge graph.
- Bridge exchange immutability: offers and blobs are content-addressed and immutable; any hash mismatch is fatal.
- Bridge provenance: every offer must trace to a VALID `RESULT_VERIFY` event in a VALID publisher node.
- Import localization: imported blobs must be materialized under the importer node and referenced only via node-local paths.
- Root-anchored paths: `@ROOT/` is the only allowed prefix for root-level bridge exchange paths; `..` is always forbidden.
- Graph report required: the root must output `swarm_graph_report_v1.json`, and the verifier must recompute and match it exactly.

ICORE lock hash derivation order (normative for v3.2):

- `lock_id` is computed from the lock with `lock_id` removed and `lock_head_hash` set to "__SELF__".
- `lock_head_hash` is computed from the lock with `lock_head_hash` removed and `lock_id` set to the computed value.

This document is normative for META_HASH computation in v3.2.
