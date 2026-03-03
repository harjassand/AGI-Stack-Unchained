# v11_3

> Path: `CDEL-v2/cdel/v11_3`

## Mission

Core verifier/runtime implementation for CDEL protocol versions and shared primitives.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `tests_sas_math/`: tests and validation assets.

## Key Files

- `__init__.py`: Python module or executable script.
- `sas_conjecture_generator_v2.py`: Python module or executable script.
- `sas_conjecture_generator_v3.py`: Python module or executable script.
- `sas_conjecture_ir_v2.py`: Python module or executable script.
- `sas_conjecture_ir_v3.py`: Python module or executable script.
- `sas_conjecture_seed_v2.py`: Python module or executable script.
- `sas_conjecture_seed_v3.py`: Python module or executable script.
- `sas_conjecture_selection_v2.py`: Python module or executable script.
- `sas_conjecture_selection_v3.py`: Python module or executable script.
- `sas_conjecture_triviality_v2.py`: Python module or executable script.
- `sas_conjecture_triviality_v3.py`: Python module or executable script.
- `sealed_sas_conjecture_gen_worker_v2.py`: Python module or executable script.
- `sealed_sas_conjecture_gen_worker_v3.py`: Python module or executable script.
- `verify_rsi_sas_math_v2.py`: Python module or executable script.
- `verify_rsi_sas_math_v3.py`: Python module or executable script.

## File-Type Surface

- `py`: 15 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v11_3
find CDEL-v2/cdel/v11_3 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v11_3 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
