# flagships

> Path: `Extension-1/CDEL/experiments/flagships`

## Mission

Extension layer modules for proposal, generation, and self-improvement capabilities.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `addressability.json`: JSON contract, config, or artifact.
- `addressability_big.json`: JSON contract, config, or artifact.
- `capacity.json`: JSON contract, config, or artifact.
- `certificates.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 4 files

## Operational Checks

```bash
ls -la Extension-1/CDEL/experiments/flagships
find Extension-1/CDEL/experiments/flagships -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Extension-1/CDEL/experiments/flagships | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
