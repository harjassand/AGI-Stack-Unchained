# configs

> Path: `polymath/registry/eudrs_u/vision/perception/configs`

## Mission

Polymath registry/store logic for scouting, bootstrap, and domain conquest flows.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `sha256_0e0ee6a99acc17af94a10e984a7a83605d809448df134d821dba75f482b42e26.vision_perception_config_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 1 files

## Operational Checks

```bash
ls -la polymath/registry/eudrs_u/vision/perception/configs
find polymath/registry/eudrs_u/vision/perception/configs -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files polymath/registry/eudrs_u/vision/perception/configs | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
