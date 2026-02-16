# RSI Swarm Protocol Contract v1

This contract specifies the v3.0 swarm protocol requirements:

- Immutable core locking: the v3.0 lock must include v3.0 schemas, verifiers, swarm ledger hashing code, and coordinator commit-ordering logic.
- Attestation required: every swarm run must include a VALID immutable core receipt at the run root, plus agent receipts.
- Deterministic ledgering: swarm ledger and barrier ledger entries are hashed via GCJ-1 canonical JSON and `sha256`.
- Deterministic commit ordering: barrier updates and verification order follow `ROUND_COMMIT_V1` rules only.
- Fail-closed semantics: missing or invalid artifacts, mismatched core IDs, or nondeterminism are fatal.

ICORE lock hash derivation order (normative for v3.0):

- `lock_id` is computed from the lock with `lock_id` removed and `lock_head_hash` set to "__SELF__".
- `lock_head_hash` is computed from the lock with `lock_head_hash` removed and `lock_id` set to the computed value.

This document is normative for META_HASH computation in v3.0.
