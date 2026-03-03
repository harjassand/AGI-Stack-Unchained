# v19_smoke

> Path: `tools/v19_smoke`

## Mission

Operational and developer tooling used across stack build, run, and validation workflows.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `run_gate_matrix_e2e.py`: Python module or executable script.
- `run_promotion_gate_smoke.py`: Python module or executable script.
- `run_tick_gate_matrix_e2e.py`: Python module or executable script.

## File-Type Surface

- `py`: 3 files

## Operational Checks

```bash
ls -la tools/v19_smoke
find tools/v19_smoke -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files tools/v19_smoke | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
