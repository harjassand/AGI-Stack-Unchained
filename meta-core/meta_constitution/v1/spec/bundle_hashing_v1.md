# Bundle Hashing v1.4

This document defines the normative hashing model for meta-core bundles.

## A1.1 Manifest hash preimage

Define:

```
manifest_for_hash(manifest):
  m = deep_copy(manifest)
  m["bundle_hash"] = ""
  if "manifest_hash" in m:
    m["manifest_hash"] = ""
  return m
```

Do **not** blank `proofs.proof_bundle_hash` unless a real cycle exists.

## A1.2 manifest_hash

```
manifest_hash = sha256( GCJ1( manifest_for_hash(manifest) ) )
```

## A1.3 proof_bundle_hash

`proofs/proof_bundle.manifest.json` **must not** reference `bundle_hash`.

Define:

```
proof_bundle_hash = sha256( GCJ1( proof_bundle.manifest.json ) )
```

## A1.4 bundle_hash

The bundle is a deterministic set of blobs:

- `constitution.manifest.json` canonical bytes
- all referenced ruleset files
- all referenced proof bundle files
- migration bundle files (if any)
- referenced schemas (if any)

Define:

```
bundle_hash =
  sha256(
    manifest_hash ||
    "\0" ||
    ruleset_hash ||
    "\0" ||
    proof_bundle_hash ||
    "\0" ||
    migration_hash_or_empty ||
    "\0" ||
    state_schema_hash ||
    "\0" ||
    toolchain_merkle_root
  )
```

The separators are literal `0x00` bytes, not the string `"\\0"`.

For v1.4:

- `migration_hash_or_empty` is the sha256 of GCJ1 canonical bytes of
  `ruleset/migrate.ir.json`.
- `state_schema_hash` is the sha256 of raw bytes of
  `meta_constitution/v1/schemas/migration.schema.json`.
- `toolchain_merkle_root` is defined in `toolchain_merkle_root_v1.md`.
