# experiments

> Path: `CDEL-v2/experiments`

## Mission

Local component subtree within the AGI stack; maintain deterministic, contract-safe changes.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `flagships/`: component subtree.

## Key Files

- `matrix.json`: JSON contract, config, or artifact.
- `matrix_mid.json`: JSON contract, config, or artifact.
- `matrix_quick.json`: JSON contract, config, or artifact.
- `replicates.json`: JSON contract, config, or artifact.
- `run_matrix.py`: Python module or executable script.
- `run_one.py`: Python module or executable script.
- `run_replicates.py`: Python module or executable script.

## File-Type Surface

- `json`: 4 files
- `py`: 3 files

## Operational Checks

```bash
ls -la CDEL-v2/experiments
find CDEL-v2/experiments -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/experiments | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
