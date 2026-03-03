# config

> Path: `tools/genesis_engine/config`

## Mission

Operational and developer tooling used across stack build, run, and validation workflows.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `ge_config_v1.json`: JSON contract, config, or artifact.
- `ge_config_v1.md`: documentation artifact.

## File-Type Surface

- `md`: 1 files
- `json`: 1 files

## Operational Checks

```bash
ls -la tools/genesis_engine/config
find tools/genesis_engine/config -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files tools/genesis_engine/config | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
