# pins

> Path: `CDEL-v2/cdel/v19_0/federation/pins`

## Mission

Core verifier/runtime implementation for CDEL protocol versions and shared primitives.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `ok_canonicalization_profile_v1.json`: JSON contract, config, or artifact.
- `ok_overlap_signature_v1.json`: JSON contract, config, or artifact.
- `ok_refutation_witness_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 3 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v19_0/federation/pins
find CDEL-v2/cdel/v19_0/federation/pins -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v19_0/federation/pins | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
