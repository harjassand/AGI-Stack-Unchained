# CAOE v1.1 Specpack

Purpose
- Define the normative, deterministic artifact formats for CAOE v1.1.
- Provide canonicalization rules, hashing rules, schemas, and vectors for cross-repo consistency.

Threat model
- Proposer is untrusted and may attempt to smuggle nondeterminism or malformed artifacts.
- Certifier must validate schemas, canonicalization, and deterministic packaging.

Required invariants
- Canonical JSON bytes follow the exact rule in `CANONICALIZATION.md`.
- `ontology_hash` and `candidate_id` use the self-referential hash rules in `CANONICALIZATION.md`.
- Tar packaging is deterministic per `TAR_DETERMINISM.md`.
- All artifacts conform to the schemas in `SCHEMAS/`.
- Canonicalization vectors in `VECTORS/` reproduce exact sha256 values.

Scope
- Applies to CAOE v1.1 artifacts across RE1/RE2/RE3.
- Suitepack remains `caoe_suitepack_v1` (not versioned here).
