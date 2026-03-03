# indexes

> Path: `polymath/store/indexes`

## Mission

Polymath registry/store logic for scouting, bootstrap, and domain conquest flows.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `domain_to_artifacts.jsonl`: project artifact.
- `urls_to_sha256.jsonl`: project artifact.

## File-Type Surface

- `jsonl`: 2 files

## Operational Checks

```bash
ls -la polymath/store/indexes
find polymath/store/indexes -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files polymath/store/indexes | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
