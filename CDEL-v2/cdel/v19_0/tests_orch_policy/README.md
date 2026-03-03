# tests_orch_policy

> Path: `CDEL-v2/cdel/v19_0/tests_orch_policy`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `test_microkernel_policy_bonus_determinism_v1.py`: Python module or executable script.
- `test_orch_policy_activation_pointer_atomicity_v1.py`: Python module or executable script.
- `test_orch_policy_eval_gates_v1.py`: Python module or executable script.
- `test_refutation_leak_guard_policy_eval_v1.py`: Python module or executable script.
- `test_verifier_recomputes_policy_bonus_v1.py`: Python module or executable script.

## File-Type Surface

- `py`: 5 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v19_0/tests_orch_policy
find CDEL-v2/cdel/v19_0/tests_orch_policy -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v19_0/tests_orch_policy | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
