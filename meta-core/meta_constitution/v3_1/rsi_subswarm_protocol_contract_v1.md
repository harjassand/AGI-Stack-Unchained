# RSI Subswarm Protocol Contract v1

This contract specifies the v3.1 recursive swarm protocol requirements:

- Immutable core locking: the v3.1 lock must include v3.1 schemas, verifiers, swarm ledger hashing logic, and coordinator/worker code that governs spawn/join ordering and path rules.
- Attestation required: every swarm node (root + descendants) must include a VALID immutable core receipt at the node root, plus agent receipts.
- Deterministic ledgering: swarm ledger and barrier ledger entries are hashed via GCJ-1 canonical JSON and `sha256`.
- Event ref-hash rules: `event_ref_hash` is used for cross-ledger references; cycle-breaking event types compute `event_ref_hash` with excluded payload fields.
- Recursive verification: child packs must link back to their parent, and the verifier must fail closed on any parent-link mismatch, cycle, depth limit, or node limit violation.
- Non-stalling joins: the root barrier ledger must be allowed to advance even when child swarms are not yet joined.

ICORE lock hash derivation order (normative for v3.1):

- `lock_id` is computed from the lock with `lock_id` removed and `lock_head_hash` set to "__SELF__".
- `lock_head_hash` is computed from the lock with `lock_head_hash` removed and `lock_id` set to the computed value.

This document is normative for META_HASH computation in v3.1.
