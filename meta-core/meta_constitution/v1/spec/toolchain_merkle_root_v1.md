# Toolchain Merkle Root v1

This document defines the canonical toolchain merkle root used by the kernel and audit.

## Inputs (fixed allowlist)

All paths are relative to the meta-core repository root:

- `kernel/verifier/toolchain.lock`
- `kernel/verifier/Cargo.lock`
- `kernel/verifier/KERNEL_HASH`
- `kernel/verifier/build.sh`
- `meta_constitution/v1/META_HASH`
- `meta_constitution/v1/build_meta_hash.sh`
- `scripts/build.sh`

The list is fixed for v1 and ordered lexicographically by path in the algorithm.

## Algorithm

For each file:

1. Read raw bytes.
2. Compute `sha256(bytes)`.

Build the JSON object:

```
{
  "version": 1,
  "files": [
    { "path": "...", "sha256": "...", "bytes": <int> },
    ...
  ]
}
```

Sort `files` lexicographically by `path`.

Finally:

```
toolchain_merkle_root = sha256( GCJ1( that_json_object ) )
```
