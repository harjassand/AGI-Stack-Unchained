# tests_sas_system

> Path: `CDEL-v2/cdel/v14_0/tests_sas_system`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `__init__.py`: Python module or executable script.
- `test_build_offline_required.py`: Python module or executable script.
- `test_equivalence_mismatch.py`: Python module or executable script.
- `test_proof_validation.py`: Python module or executable script.
- `test_registry_delta.py`: Python module or executable script.
- `test_rust_forbidden_tokens.py`: Python module or executable script.
- `test_vendor_recovery.py`: Python module or executable script.
- `test_verifier_writable_crate_workspace.py`: Python module or executable script.

## File-Type Surface

- `py`: 8 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v14_0/tests_sas_system
find CDEL-v2/cdel/v14_0/tests_sas_system -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v14_0/tests_sas_system | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
