# safety

> Path: `CDEL-v2/sealed_suites/safety`

## Mission

Local component subtree within the AGI stack; maintain deterministic, contract-safe changes.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `eae791c9563e5a54292bd019c863a40e09e8891a5a2424e91c0143f7a55fcc96.jsonl`: project artifact.

## File-Type Surface

- `jsonl`: 1 files

## Operational Checks

```bash
ls -la CDEL-v2/sealed_suites/safety
find CDEL-v2/sealed_suites/safety -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/sealed_suites/safety | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
