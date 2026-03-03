# kernel

> Path: `Extension-1/CDEL/cdel/kernel`

## Mission

Extension layer modules for proposal, generation, and self-improvement capabilities.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `__init__.py`: Python module or executable script.
- `ast.py`: Python module or executable script.
- `canon.py`: Python module or executable script.
- `cost.py`: Python module or executable script.
- `deps.py`: Python module or executable script.
- `eval.py`: Python module or executable script.
- `parse.py`: Python module or executable script.
- `proof.py`: Python module or executable script.
- `spec.py`: Python module or executable script.
- `terminate.py`: Python module or executable script.
- `typecheck.py`: Python module or executable script.
- `types.py`: Python module or executable script.

## File-Type Surface

- `py`: 12 files

## Operational Checks

```bash
ls -la Extension-1/CDEL/cdel/kernel
find Extension-1/CDEL/cdel/kernel -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Extension-1/CDEL/cdel/kernel | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
