# v19_0

> Path: `CDEL-v2/cdel/v19_0`

## Mission

Core verifier/runtime implementation for CDEL protocol versions and shared primitives.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `continuity/`: component subtree.
- `epistemic/`: component subtree.
- `federation/`: component subtree.
- `orch_bandit/`: component subtree.
- `rust/`: component subtree.
- `tests_continuity/`: tests and validation assets.
- `tests_kernel_env_constitution/`: tests and validation assets.
- `tests_mission/`: tests and validation assets.
- `tests_omega_daemon/`: tests and validation assets.
- `tests_orch_bandit/`: tests and validation assets.
- `tests_orch_policy/`: tests and validation assets.
- `tests_orch_rl/`: tests and validation assets.
- `tests_orch_worldmodel/`: tests and validation assets.
- `tests_proposer_models/`: tests and validation assets.
- `tests_training/`: tests and validation assets.
- `tests_world_federation/`: tests and validation assets.
- `world/`: component subtree.

## Key Files

- `__init__.py`: Python module or executable script.
- `campaign_epistemic_certify_v1.py`: Python module or executable script.
- `campaign_epistemic_reduce_v1.py`: Python module or executable script.
- `campaign_epistemic_retention_harden_v1.py`: Python module or executable script.
- `campaign_epistemic_type_governance_v1.py`: Python module or executable script.
- `common_v1.py`: Python module or executable script.
- `conservatism_v1.py`: Python module or executable script.
- `determinism_witness_v1.py`: Python module or executable script.
- `mission_store_v1.py`: Python module or executable script.
- `nontriviality_cert_v1.py`: Python module or executable script.
- `omega_promoter_v1.py`: Python module or executable script.
- `policy_vm_stark_runner_v1.py`: Python module or executable script.
- `shadow_airlock_v1.py`: Python module or executable script.
- `shadow_corpus_v1.py`: Python module or executable script.
- `shadow_fs_guard_v1.py`: Python module or executable script.
- `shadow_invariance_v1.py`: Python module or executable script.
- `shadow_j_eval_v1.py`: Python module or executable script.
- `shadow_runner_v1.py`: Python module or executable script.
- `verify_coordinator_isa_program_v1.py`: Python module or executable script.
- `verify_coordinator_opcode_table_v1.py`: Python module or executable script.
- `verify_counterfactual_trace_example_v1.py`: Python module or executable script.
- `verify_hint_bundle_v1.py`: Python module or executable script.
- `verify_inputs_descriptor_v1.py`: Python module or executable script.
- `verify_kernel_extension_proposal_v1.py`: Python module or executable script.
- `verify_merged_hint_state_v1.py`: Python module or executable script.
- ... and 17 more files.

## File-Type Surface

- `py`: 42 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v19_0
find CDEL-v2/cdel/v19_0 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v19_0 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
