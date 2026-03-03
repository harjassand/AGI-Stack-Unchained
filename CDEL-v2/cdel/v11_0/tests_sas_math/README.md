# tests_sas_math

> Path: `CDEL-v2/cdel/v11_0/tests_sas_math`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `__init__.py`: Python module or executable script.
- `test_sas_math_missing_enable_boundless_math.py`: Python module or executable script.
- `test_sas_math_missing_enable_model_genesis.py`: Python module or executable script.
- `test_sas_math_missing_sealed_receipt.py`: Python module or executable script.
- `test_sas_math_no_improvement.py`: Python module or executable script.
- `test_sas_math_non_q32_value.py`: Python module or executable script.
- `test_sas_math_proof_hash_mismatch.py`: Python module or executable script.
- `test_sas_math_root_canon_mismatch.py`: Python module or executable script.
- `test_sas_math_valid_full.py`: Python module or executable script.
- `utils.py`: Python module or executable script.

## File-Type Surface

- `py`: 10 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v11_0/tests_sas_math
find CDEL-v2/cdel/v11_0/tests_sas_math -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v11_0/tests_sas_math | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
