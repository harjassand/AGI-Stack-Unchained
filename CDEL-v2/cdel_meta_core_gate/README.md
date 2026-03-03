# cdel_meta_core_gate

> Path: `CDEL-v2/cdel_meta_core_gate`

## Mission

Local component subtree within the AGI stack; maintain deterministic, contract-safe changes.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `__init__.py`: Python module or executable script.
- `cli.py`: Python module or executable script.
- `domain.py`: Python module or executable script.
- `errors.py`: Python module or executable script.
- `inject.py`: Python module or executable script.
- `runner.py`: Python module or executable script.

## File-Type Surface

- `py`: 6 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel_meta_core_gate
find CDEL-v2/cdel_meta_core_gate -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel_meta_core_gate | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
