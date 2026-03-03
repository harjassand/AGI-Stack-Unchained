# v13_0

> Path: `CDEL-v2/cdel/v13_0`

## Mission

Core verifier/runtime implementation for CDEL protocol versions and shared primitives.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `tests_sas_science/`: tests and validation assets.

## Key Files

- `__init__.py`: Python module or executable script.
- `sas_science_canon_v1.py`: Python module or executable script.
- `sas_science_dataset_v1.py`: Python module or executable script.
- `sas_science_eval_v1.py`: Python module or executable script.
- `sas_science_fit_v1.py`: Python module or executable script.
- `sas_science_generator_v1.py`: Python module or executable script.
- `sas_science_ir_v1.py`: Python module or executable script.
- `sas_science_ledger_v1.py`: Python module or executable script.
- `sas_science_math_v1.py`: Python module or executable script.
- `sas_science_selection_v1.py`: Python module or executable script.
- `sas_science_workmeter_v1.py`: Python module or executable script.
- `sealed_science_eval_client_v1.py`: Python module or executable script.
- `sealed_science_eval_v1.py`: Python module or executable script.
- `sealed_science_eval_worker_v1.py`: Python module or executable script.
- `verify_rsi_sas_science_v1.py`: Python module or executable script.

## File-Type Surface

- `py`: 15 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v13_0
find CDEL-v2/cdel/v13_0 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v13_0 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
