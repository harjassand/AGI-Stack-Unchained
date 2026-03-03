# certs

> Path: `polymath/registry/eudrs_u/certs`

## Mission

Polymath registry/store logic for scouting, bootstrap, and domain conquest flows.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `sha256_9e2d39f7585d71517e16b5a5ea806788bc1796828e08aeb518124b36c801b8cd.universality_cert_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 1 files

## Operational Checks

```bash
ls -la polymath/registry/eudrs_u/certs
find polymath/registry/eudrs_u/certs -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files polymath/registry/eudrs_u/certs | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
