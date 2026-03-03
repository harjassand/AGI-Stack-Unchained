# components

> Path: `Genesis/genesis/genesis/components_v1_1/components`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `89bd7413eec02fec96acd369be1accfb189a973fce00e20f476a9312e2053094.json`: JSON contract, config, or artifact.
- `b42dc2e1b6af1f6912536a464b96c66ec811e41ff74aaa2daa2d6cbf9420767e.json`: JSON contract, config, or artifact.
- `cdec419f2c1ab098b4c6e97938a5cb96538e2e4c6a298cc849a0f01232c470ee.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 3 files

## Operational Checks

```bash
ls -la Genesis/genesis/genesis/components_v1_1/components
find Genesis/genesis/genesis/components_v1_1/components -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/genesis/genesis/components_v1_1/components | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
