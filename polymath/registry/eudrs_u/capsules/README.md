# capsules

> Path: `polymath/registry/eudrs_u/capsules`

## Mission

Polymath registry/store logic for scouting, bootstrap, and domain conquest flows.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `sha256_008e9bc7d975e80e2a5f407cf2f26e53ecc17aea693e4b5c8113533f73bacc28.urc_capsule_v1.bin`: project artifact.
- `sha256_23af01e3a43e2ea1f9d44f695a81f10c0a448e80f07681eed868175760a78ef5.urc_capsule_v1.bin`: project artifact.
- `sha256_330c18aed2ba04fc8a4341acf6babc97b14b53d1e7efeba7043272dec0e532ed.urc_capsule_v1.bin`: project artifact.
- `sha256_976abf9f6df7b1790f303ab1c06cab3a2f938b952681c7ba1d375a97e2d2fac9.urc_capsule_v1.bin`: project artifact.
- `sha256_b32a2a7de0715d56f50f15bbc306ab36d3c82175359ca88838b6befd53fc10e2.urc_capsule_v1.bin`: project artifact.
- `sha256_c7b1e374c0c8a20f008989d8b4bdfc01614794d8dd5ecfed4e757946d5509b7c.urc_capsule_def_v1.json`: JSON contract, config, or artifact.
- `sha256_dad5b9686383392ea41b535218d5a0c24e963268d34ef254ce6646101516bdef.urc_capsule_def_v1.json`: JSON contract, config, or artifact.
- `sha256_ded5d63117005a84eb139adea3e03b02b8ab58a083ae2f9419f820943aed9418.urc_capsule_registry_v1.json`: JSON contract, config, or artifact.
- `sha256_edb265ad8ac9cab75dfd2aea1c213141e91afb1c9c5a197fcbabb081bf5cac3f.urc_capsule_v1.bin`: project artifact.
- `sha256_fa74bdfdac2c089946deede922d5bf652db3cacd6f6320e12f7d79655175eb6f.urc_capsule_def_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `bin`: 6 files
- `json`: 4 files

## Operational Checks

```bash
ls -la polymath/registry/eudrs_u/capsules
find polymath/registry/eudrs_u/capsules -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files polymath/registry/eudrs_u/capsules | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
