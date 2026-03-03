# bench

> Path: `CDEL-v2/cdel/bench`

## Mission

Core verifier/runtime implementation for CDEL protocol versions and shared primitives.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `__init__.py`: Python module or executable script.
- `evidence_suite.py`: Python module or executable script.
- `experiment.py`: Python module or executable script.
- `run.py`: Python module or executable script.
- `solve_scoreboard.py`: Python module or executable script.
- `solve_suite.py`: Python module or executable script.
- `solve_suite_ablations.py`: Python module or executable script.
- `summarize.py`: Python module or executable script.
- `taxonomy.py`: Python module or executable script.

## File-Type Surface

- `py`: 9 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/bench
find CDEL-v2/cdel/bench -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/bench | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
