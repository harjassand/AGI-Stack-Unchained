# tests_sas_val

> Path: `CDEL-v2/cdel/v17_0/tests_sas_val`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `__init__.py`: Python module or executable script.
- `conftest.py`: pytest shared fixtures and hooks.
- `test_downstream_receipts.py`: Python module or executable script.
- `test_exec_requires_safe_receipt.py`: Python module or executable script.
- `test_full_verify_valid.py`: Python module or executable script.
- `test_guard_pages_catch_oob_crash.py`: Python module or executable script.
- `test_hotloop_dominant_pilot.py`: Python module or executable script.
- `test_native_exec_smoke_arm64_only.py`: Python module or executable script.
- `test_perf_valcycles_gate.py`: Python module or executable script.
- `test_redteam_expected_fail_codes.py`: Python module or executable script.
- `test_rejects_rw_exec.py`: Python module or executable script.
- `test_schema_validator_cache.py`: Python module or executable script.
- `test_semantic_identity.py`: Python module or executable script.
- `test_simd_neon_gate.py`: Python module or executable script.
- `test_spawn_gate.py`: Python module or executable script.
- `test_trace_complete.py`: Python module or executable script.
- `test_trace_row_fields.py`: Python module or executable script.
- `test_v16_1_smoke_fallback.py`: Python module or executable script.
- `test_val_decoder_fuzz.py`: Python module or executable script.
- `test_val_dual_decoder_parity.py`: Python module or executable script.
- `test_val_dual_lifter_parity.py`: Python module or executable script.
- `test_val_rejects_indirect_branch.py`: Python module or executable script.
- `test_val_rejects_oob_mem.py`: Python module or executable script.
- `test_val_rejects_sp_use.py`: Python module or executable script.
- `test_val_rejects_svc.py`: Python module or executable script.
- ... and 1 more files.

## File-Type Surface

- `py`: 26 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v17_0/tests_sas_val
find CDEL-v2/cdel/v17_0/tests_sas_val -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v17_0/tests_sas_val | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
