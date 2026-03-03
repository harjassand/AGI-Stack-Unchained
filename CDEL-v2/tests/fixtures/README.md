# fixtures

> Path: `CDEL-v2/tests/fixtures`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `module1.json`: JSON contract, config, or artifact.
- `module2.json`: JSON contract, config, or artifact.
- `module_a.json`: JSON contract, config, or artifact.
- `module_b.json`: JSON contract, config, or artifact.
- `module_c.json`: JSON contract, config, or artifact.
- `module_proof_invalid.json`: JSON contract, config, or artifact.
- `module_proof_unbounded_missing.json`: JSON contract, config, or artifact.
- `module_proof_valid.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 8 files

## Operational Checks

```bash
ls -la CDEL-v2/tests/fixtures
find CDEL-v2/tests/fixtures -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/tests/fixtures | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
