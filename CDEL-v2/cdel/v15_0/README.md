# v15_0

> Path: `CDEL-v2/cdel/v15_0`

## Mission

Core verifier/runtime implementation for CDEL protocol versions and shared primitives.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `lean/`: component subtree.
- `rust/`: component subtree.
- `tests_sas_kernel/`: tests and validation assets.

## Key Files

- `__init__.py`: Python module or executable script.
- `kernel_activation_v1.py`: Python module or executable script.
- `kernel_equivalence_v1.py`: Python module or executable script.
- `kernel_hash_tree_v1.py`: Python module or executable script.
- `kernel_ledger_v1.py`: Python module or executable script.
- `kernel_perf_v1.py`: Python module or executable script.
- `kernel_pinning_v1.py`: Python module or executable script.
- `kernel_plan_ir_v1.py`: Python module or executable script.
- `kernel_policy_v1.py`: Python module or executable script.
- `kernel_registry_v2.py`: Python module or executable script.
- `kernel_run_spec_v1.py`: Python module or executable script.
- `kernel_sealed_runner_v1.py`: Python module or executable script.
- `kernel_snapshot_v1.py`: Python module or executable script.
- `kernel_trace_v1.py`: Python module or executable script.
- `verify_rsi_sas_kernel_v1.py`: Python module or executable script.

## File-Type Surface

- `py`: 15 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v15_0
find CDEL-v2/cdel/v15_0 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v15_0 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
