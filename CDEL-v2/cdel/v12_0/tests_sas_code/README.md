# tests_sas_code

> Path: `CDEL-v2/cdel/v12_0/tests_sas_code`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `.pytest_cache/`: component subtree.

## Key Files

- `__init__.py`: Python module or executable script.
- `test_attempt_proof_cannot_define_bubblesort.py`: Python module or executable script.
- `test_end_to_end_valid_fixture.py`: Python module or executable script.
- `test_forbidden_token_scan_rejects_sorry.py`: Python module or executable script.
- `test_ir_hash_determinism.py`: Python module or executable script.
- `test_perf_gate_rejects_insertion_sort.py`: Python module or executable script.
- `test_perf_policy_cannot_disable_scaling_sanity.py`: Python module or executable script.
- `test_perf_policy_cannot_relax_threshold.py`: Python module or executable script.
- `test_preamble_bubbleiter_cannot_call_mergesort.py`: Python module or executable script.
- `test_preamble_bubblesort_cannot_alias_mergesort.py`: Python module or executable script.
- `test_preamble_forbidden_builtin_sort_rejected.py`: Python module or executable script.
- `test_preamble_hash_mismatch_fail_closed.py`: Python module or executable script.
- `test_proof_semantics_tamper_rejected.py`: Python module or executable script.
- `test_toolchain_manifest_cannot_be_wrapper.py`: Python module or executable script.
- `test_verifier_fail_closed_missing_artifact.py`: Python module or executable script.
- `test_verifier_rejects_fake_permutation.py`: Python module or executable script.
- `test_verifier_rejects_identity_sort.py`: Python module or executable script.
- `test_verifier_replay_determinism.py`: Python module or executable script.
- `utils.py`: Python module or executable script.

## File-Type Surface

- `py`: 19 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v12_0/tests_sas_code
find CDEL-v2/cdel/v12_0/tests_sas_code -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v12_0/tests_sas_code | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
