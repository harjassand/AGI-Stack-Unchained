# Constitutional Hardening Contract v1

This contract specifies the v2.3 immutable-core hardening requirements:

- Immutable core locking: a pinned immutable core file set is hashed and verified by the RE1 verifier.
- Attestation required: each v2.3 run must include a VALID immutable core receipt.
- Patch non-interference: any patch touching an immutable-core file is rejected.
- Verifier immutability: all verification logic is inside the immutable core.
- Fail-closed semantics: missing or invalid immutable core attestations are fatal.

ICORE lock hash derivation order (normative for v2.3):

- `lock_id` is computed from the lock with `lock_id` removed and `lock_head_hash` set to "__SELF__".
- `lock_head_hash` is computed from the lock with `lock_head_hash` removed and `lock_id` set to the computed value.

This document is normative for META_HASH computation in v2.3.
