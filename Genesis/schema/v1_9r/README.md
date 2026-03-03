# v1_9r

> Path: `Genesis/schema/v1_9r`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `autonomy_manifest_v1.jsonschema`: JSON Schema contract.
- `rsi_real_demon_campaign_pack_v5.jsonschema`: JSON Schema contract.

## File-Type Surface

- `jsonschema`: 2 files

## Operational Checks

```bash
ls -la Genesis/schema/v1_9r
find Genesis/schema/v1_9r -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/schema/v1_9r | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
