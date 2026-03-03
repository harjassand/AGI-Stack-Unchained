# v11_1

> Path: `CDEL-v2/cdel/v11_1`

## Mission

Core verifier/runtime implementation for CDEL protocol versions and shared primitives.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `tests/`: tests and validation assets.
- `tests_sas_math/`: tests and validation assets.

## Key Files

- `__init__.py`: Python module or executable script.
- `arch_bundle.py`: Python module or executable script.
- `arch_synthesis_ledger.py`: Python module or executable script.
- `architecture_builder_v1.py`: Python module or executable script.
- `fixed_q32_v1.py`: Python module or executable script.
- `novelty_v1.py`: Python module or executable script.
- `path_canon_v1.py`: Python module or executable script.
- `sas_conjecture_generator_v1.py`: Python module or executable script.
- `sas_conjecture_ir_v1.py`: Python module or executable script.
- `sas_conjecture_seed_v1.py`: Python module or executable script.
- `sas_math_eval_v1.py`: Python module or executable script.
- `sas_math_fingerprint_v1.py`: Python module or executable script.
- `sas_math_ledger.py`: Python module or executable script.
- `sas_math_policy_ir_v1.py`: Python module or executable script.
- `sealed_arch_build_worker_v1.py`: Python module or executable script.
- `sealed_arch_eval_heldout_worker_v1.py`: Python module or executable script.
- `sealed_arch_eval_worker_v1.py`: Python module or executable script.
- `sealed_arch_training_worker_v1.py`: Python module or executable script.
- `sealed_sas_conjecture_gen_worker_v1.py`: Python module or executable script.
- `sealed_sas_math_attempt_worker_v1.py`: Python module or executable script.
- `topology_fingerprint_v1.py`: Python module or executable script.
- `verify_rsi_arch_synthesis_v1.py`: Python module or executable script.
- `verify_rsi_sas_math_v1.py`: Python module or executable script.

## File-Type Surface

- `py`: 23 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v11_1
find CDEL-v2/cdel/v11_1 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v11_1 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
