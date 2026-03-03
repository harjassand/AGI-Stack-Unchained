# tests_fast

> Path: `CDEL-v2/cdel/v18_0/tests_fast`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `test_dmpl_phase2_plan_call_v1_fast.py`: Python module or executable script.
- `test_dmpl_phase3_plan_replay_verifier_v1_fast.py`: Python module or executable script.
- `test_eudrs_u_fast.py`: Python module or executable script.
- `test_eudrs_u_hash_v1_fast.py`: Python module or executable script.
- `test_eudrs_u_merkle_v1_fast.py`: Python module or executable script.
- `test_eudrs_u_promotion_phase1_fast.py`: Python module or executable script.
- `test_eudrs_u_q32ops_v1_fast.py`: Python module or executable script.
- `test_mcl_phase6_fast.py`: Python module or executable script.
- `test_ml_index_io_and_gates_v1_fast.py`: Python module or executable script.
- `test_ml_index_v1_fast.py`: Python module or executable script.
- `test_pclp_stark_vm_v1_fast.py`: Python module or executable script.
- `test_polymath_phase17_fast.py`: Python module or executable script.
- `test_qxrl_v1_fast.py`: Python module or executable script.
- `test_qxrl_v1_run_verifier_fast.py`: Python module or executable script.
- `test_qxwmr_canon_wl_v1_fast.py`: Python module or executable script.
- `test_stark_vpvm_smoke_v1_fast.py`: Python module or executable script.
- `test_urc_phase7_fast.py`: Python module or executable script.
- `test_verify_qxrl_v1_pclp_path_fast.py`: Python module or executable script.
- `test_vision_stage1_v1_fast.py`: Python module or executable script.
- `test_vision_stage2_v1_fast.py`: Python module or executable script.
- `test_vpvm_q32_vm_v1_fast.py`: Python module or executable script.

## File-Type Surface

- `py`: 21 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v18_0/tests_fast
find CDEL-v2/cdel/v18_0/tests_fast -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v18_0/tests_fast | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
