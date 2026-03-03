# v14_0

> Path: `CDEL-v2/cdel/v14_0`

## Mission

Core verifier/runtime implementation for CDEL protocol versions and shared primitives.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `lean/`: component subtree.
- `runtime/`: runtime state and persistence artifacts.
- `rust/`: component subtree.
- `tests_sas_system/`: tests and validation assets.

## Key Files

- `__init__.py`: Python module or executable script.
- `sas_system_build_v1.py`: Python module or executable script.
- `sas_system_codegen_rust_v1.py`: Python module or executable script.
- `sas_system_equivalence_v1.py`: Python module or executable script.
- `sas_system_extract_v1.py`: Python module or executable script.
- `sas_system_immutability_v1.py`: Python module or executable script.
- `sas_system_ir_v1.py`: Python module or executable script.
- `sas_system_ledger_v1.py`: Python module or executable script.
- `sas_system_optimize_v1.py`: Python module or executable script.
- `sas_system_perf_v1.py`: Python module or executable script.
- `sas_system_proof_v1.py`: Python module or executable script.
- `sas_system_selection_v1.py`: Python module or executable script.
- `verify_rsi_sas_system_v1.py`: Python module or executable script.

## File-Type Surface

- `py`: 13 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v14_0
find CDEL-v2/cdel/v14_0 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v14_0 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
