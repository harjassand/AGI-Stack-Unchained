# tests_sas_kernel_v15_1

> Path: `CDEL-v2/cdel/v15_1/tests_sas_kernel_v15_1`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `__init__.py`: Python module or executable script.
- `test_brain_determinism.py`: Python module or executable script.
- `test_brain_parity_suite.py`: Python module or executable script.
- `test_casecount_ge_100.py`: Python module or executable script.
- `test_negative_spawn_forbidden_orchestrator.py`: Python module or executable script.
- `test_no_trivial_safety_proofs.py`: Python module or executable script.
- `test_perf_gate_1000x.py`: Python module or executable script.
- `test_perf_gate_reject_zero_candidate.py`: Python module or executable script.
- `test_perf_report_consistency.py`: Python module or executable script.
- `test_proof_replay.py`: Python module or executable script.
- `test_proof_replay_negative.py`: Python module or executable script.
- `test_proof_replay_positive.py`: Python module or executable script.
- `test_run_contains_orchestrator_sources_or_bundle.py`: Python module or executable script.
- `test_toolchain_hash_mismatch.py`: Python module or executable script.
- `test_toolchain_reject_true.py`: Python module or executable script.
- `utils.py`: Python module or executable script.

## File-Type Surface

- `py`: 16 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v15_1/tests_sas_kernel_v15_1
find CDEL-v2/cdel/v15_1/tests_sas_kernel_v15_1 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v15_1/tests_sas_kernel_v15_1 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
