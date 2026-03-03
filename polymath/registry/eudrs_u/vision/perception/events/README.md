# events

> Path: `polymath/registry/eudrs_u/vision/perception/events`

## Mission

Polymath registry/store logic for scouting, bootstrap, and domain conquest flows.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `sha256_433a6b668e4d6688404b988115fdca860cd80d098faa1860f86673f519c4f93d.vision_event_manifest_v1.json`: JSON contract, config, or artifact.
- `sha256_4c9e9d01fb3ff1400da2b06c3acbfa2ab692aa7456adbe30d03b86e4375d9fc5.vision_event_manifest_v1.json`: JSON contract, config, or artifact.
- `sha256_6accdb9b3e85c0ebce79e287d0dc91341ed35de9e9eeb1f2607b151541343222.vision_event_manifest_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 3 files

## Operational Checks

```bash
ls -la polymath/registry/eudrs_u/vision/perception/events
find polymath/registry/eudrs_u/vision/perception/events -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files polymath/registry/eudrs_u/vision/perception/events | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
