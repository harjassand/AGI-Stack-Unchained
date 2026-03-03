# manifests

> Path: `polymath/registry/eudrs_u/manifests`

## Mission

Polymath registry/store logic for scouting, bootstrap, and domain conquest flows.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `sha256_3158e21d9ae5dee2321a12a149688a60c17fd2be66e967c37932cfff282c7bef.qxrl_invsqrt_lut_manifest_v1.json`: JSON contract, config, or artifact.
- `sha256_b51460e334eb6c8417faef6ea2ffe600938d1b59c6dd3a261dd08f2cacc4ba5a.qxwmr_world_model_manifest_v1.json`: JSON contract, config, or artifact.
- `sha256_f6b7eac00dae22340aefefc36692994958acb88933698f97968ae9cb37e97864.qxrl_invsqrt_lut_v1.bin`: project artifact.

## File-Type Surface

- `json`: 2 files
- `bin`: 1 files

## Operational Checks

```bash
ls -la polymath/registry/eudrs_u/manifests
find polymath/registry/eudrs_u/manifests -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files polymath/registry/eudrs_u/manifests | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
