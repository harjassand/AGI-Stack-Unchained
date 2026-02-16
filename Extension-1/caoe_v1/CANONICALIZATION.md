# CAOE v1 proposer canonicalization

## Canonical JSON bytes
`canonical_json_bytes(obj)` produces UTF-8 bytes with:
- sorted keys
- minimal separators (no spaces)
- LF line endings
- list order preserved
- NaN/Infinity disallowed (fail-closed)

## Deterministic ordering
- candidates sorted by `(operator_rank, predicted_priority, candidate_id)`
  - `operator_rank`: descending by operator weight, then `op_id` lex
  - `predicted_priority`: lower is better
- anomaly regimes sorted by `(success asc, efficiency asc, regime_id lex)`

## Hashes (sha256 hex)
- `ontology_hash = sha256_hex(canonical_json_bytes(ontology_spec))`
- `mech_hash = sha256_hex(canonical_json_bytes(mechanism_registry))`

## Candidate ID
Candidate ID is computed exactly as in CDEL CAOE v1:

```
canonical_manifest_bytes = canonical_json_bytes(manifest.json)
patch_hash_bytes = bytes.fromhex(sha256_hex(canonical_json_bytes(ontology_patch.json)))
mech_diff_hash_bytes = bytes.fromhex(sha256_hex(canonical_json_bytes(mechanism_registry_diff.json or {})))
programs_hash_bytes = bytes.fromhex(sha256_hex(concat_program_bytes_in_sorted_path_order))

candidate_id = sha256_hex(
  canonical_manifest_bytes || patch_hash_bytes || mech_diff_hash_bytes || programs_hash_bytes
)
```

Program bytes are concatenated in sorted path order (e.g., `programs/lambda.bp`, `programs/phi.bp`, `programs/psi.bp`).

## Deterministic tar rules
- Sorted entry order
- `mtime=0`, `uid=gid=0`, `uname=gname="root"`
- No pax timestamps/headers
- No symlinks or hardlinks
- Permissions: files `0644`, dirs `0755`
