# tests_sas_kernel

> Path: `CDEL-v2/cdel/v15_0/tests_sas_kernel`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `__init__.py`: Python module or executable script.
- `test_determinism_hashes.py`: Python module or executable script.
- `test_equivalence_omega_v4.py`: Python module or executable script.
- `test_equivalence_sas_system_v14.py`: Python module or executable script.
- `test_forbid_unsafe_and_tokens.py`: Python module or executable script.
- `test_negative_heldout_direct_read.py`: Python module or executable script.
- `test_negative_outside_root_write.py`: Python module or executable script.
- `test_negative_spawn_forbidden_orchestrator.py`: Python module or executable script.
- `test_negative_toolchain_spoof.py`: Python module or executable script.
- `test_negative_wrapper_script_kernel.py`: Python module or executable script.
- `test_negative_wrong_kernel_hash.py`: Python module or executable script.
- `utils.py`: Python module or executable script.

## File-Type Surface

- `py`: 12 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v15_0/tests_sas_kernel
find CDEL-v2/cdel/v15_0/tests_sas_kernel -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v15_0/tests_sas_kernel | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
