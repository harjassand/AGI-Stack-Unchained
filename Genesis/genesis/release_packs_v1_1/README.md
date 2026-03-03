# release_packs_v1_1

> Path: `Genesis/genesis/release_packs_v1_1`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `release_pack_536a52be9c5ae2346a72e367d8ed90eb6666717540619b9fb615e7a32dd2896e/`: component subtree.

## Key Files

- `release_pack_536a52be9c5ae2346a72e367d8ed90eb6666717540619b9fb615e7a32dd2896e.tar.gz`: project artifact.

## File-Type Surface

- `gz`: 1 files

## Operational Checks

```bash
ls -la Genesis/genesis/release_packs_v1_1
find Genesis/genesis/release_packs_v1_1 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/genesis/release_packs_v1_1 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
