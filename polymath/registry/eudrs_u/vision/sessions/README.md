# sessions

> Path: `polymath/registry/eudrs_u/vision/sessions`

## Mission

Polymath registry/store logic for scouting, bootstrap, and domain conquest flows.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `sha256_088c396d592aa2f7a1ac57c2d283bee202823a53a38de7d9ec03acb64ca84a0b.vision_session_manifest_v1.json`: JSON contract, config, or artifact.
- `sha256_4c18dfabf21ff50bbd57537c8e9571017f1fdffadd90fbc24179414a38585bfe.vision_session_manifest_v1.json`: JSON contract, config, or artifact.
- `sha256_cfd6c827164c41d7a1d8cd811f00386dfbccfb25c712e82495597e076c9a9163.vision_session_manifest_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 3 files

## Operational Checks

```bash
ls -la polymath/registry/eudrs_u/vision/sessions
find polymath/registry/eudrs_u/vision/sessions -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files polymath/registry/eudrs_u/vision/sessions | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
