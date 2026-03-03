# suite_manifests

> Path: `Extension-1/CDEL/claims/suite_manifests`

## Mission

Extension layer modules for proposal, generation, and self-improvement capabilities.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `runs_addressability_big.json`: JSON contract, config, or artifact.
- `runs_full.json`: JSON contract, config, or artifact.
- `runs_repl.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 3 files

## Operational Checks

```bash
ls -la Extension-1/CDEL/claims/suite_manifests
find Extension-1/CDEL/claims/suite_manifests -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Extension-1/CDEL/claims/suite_manifests | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
