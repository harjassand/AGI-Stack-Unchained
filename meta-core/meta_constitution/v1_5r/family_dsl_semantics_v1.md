# Family DSL Semantics v1 (Pinned)

This document pins the deterministic semantics of `family_dsl_v1` for v1.5r.

## Canonicalization

All JSON objects are canonicalized with GCJ-1:

- UTF-8 encoding
- Keys sorted lexicographically
- Separators `(',', ':')`
- No floats; integers only; fixed-point numbers encoded as strings
- No NaN/Inf

`canon_bytes(x)` is the canonical byte representation.

## AST Evaluation

Nodes:

- `CONST`: returns the GCJ-1 JSON value as-is.
- `PARAM`: returns the parameter value from `theta`.
- `BYTES`: evaluates each child to bytes and concatenates.
  - If child yields JSON, use `canon_bytes(child)`.
  - If child yields bytes, use those bytes directly.
- `SHA256`: returns 32-byte digest of its child bytes.
- `PRNG_CHACHA20`: returns `n_bytes` of ChaCha20 keystream.
  - Key = 32-byte seed (if seed length != 32, hash to 32 with SHA256).
  - Nonce = 12 bytes of zero.
  - Initial counter = 0.
- `U32_LE`: reads first 4 bytes as little-endian u32.
- `RANGE_INT`: maps u32 to `[min, max]` using rejection sampling.
- `EMIT_INSTANCE`: returns the final instance JSON.

## PRNG Definition

ChaCha20 stream cipher per RFC 8439:

- 256-bit key
- 96-bit nonce (all zero)
- Counter starts at 0

The output is the keystream bytes; no encryption is performed.

## Instance Identity

`inst_hash = sha256(canon_bytes({family_id, theta, epoch_commitment: c_t, dsl_version: 1}))`

All hashes are returned as `sha256:<hex>` strings.
