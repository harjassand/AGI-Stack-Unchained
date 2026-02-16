# Metabolism Contract v1 (v1_8r)

This contract defines the allowed metabolic optimization for v1_8r.

## Scope
- Only `ctx_hash_cache_v1` is allowlisted.
- The cache is deterministic, bounded, and FIFO-evicted.
- Cache hits must return the exact same `onto_ctx_hash` bytes as recomputation.

## Safety
- The patch may not change semantic outputs.
- The patch may only reduce work counters through caching.
- Any missing artifact, schema mismatch, or hash mismatch must fail closed.

## WorkVec v1
Counters are ordered lexicographically:
1. `sha256_calls_total`
2. `canon_calls_total`
3. `sha256_bytes_total`
4. `canon_bytes_total`
5. `onto_ctx_hash_compute_calls_total`

Caching must strictly reduce the WorkVec under this order and meet the minimum
`METAPATCH_V1_MIN_SHA256_CALL_DELTA`.
