# omega

> Path: `tools/omega`

## Mission

Operational and developer tooling used across stack build, run, and validation workflows.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `epistemics/`: component subtree.
- `native/`: component subtree.
- `tests/`: tests and validation assets.
- `verifier_corpus_v1/`: component subtree.

## Key Files

- `agi_micdrop_candidate_runner_v1.py`: Python module or executable script.
- `agi_micdrop_solver_v1.py`: Python module or executable script.
- `ek_meta_verify_v1.py`: Python module or executable script.
- `launch_micdrop_30min_v1.sh`: shell automation script.
- `launch_micdrop_novelty_v2.sh`: shell automation script.
- `launch_omega_unified_30min_v1.sh`: shell automation script.
- `launch_omega_unified_wild_infinite_v1.sh`: shell automation script.
- `launch_oracle_ladder_60min_v1.sh`: shell automation script.
- `make_meta_core_sandbox_v1.py`: Python module or executable script.
- `micdrop_devset_v2.json`: JSON contract, config, or artifact.
- `micdrop_materialize_promotions_v1.py`: Python module or executable script.
- `micdrop_novelty_packgen_v1.py`: Python module or executable script.
- `omega_benchmark_suite_composite_v1.py`: Python module or executable script.
- `omega_benchmark_suite_oracle_v1.py`: Python module or executable script.
- `omega_benchmark_suite_v1.py`: Python module or executable script.
- `omega_benchmark_suite_v19_ceiling_v1.py`: Python module or executable script.
- `omega_benchmark_suite_v19_v1.py`: Python module or executable script.
- `omega_gate_loader_v1.py`: Python module or executable script.
- `omega_llm_router_v1.py`: Python module or executable script.
- `omega_noop_reason_classifier_v1.py`: Python module or executable script.
- `omega_overnight_runner_v1.py`: Python module or executable script.
- `omega_replay_bundle_v1.py`: Python module or executable script.
- `omega_shadow_proposer_v1.py`: Python module or executable script.
- `omega_skill_manifest_v1.py`: Python module or executable script.
- `omega_test_router_v1.py`: Python module or executable script.
- ... and 10 more files.

## File-Type Surface

- `py`: 29 files
- `sh`: 5 files
- `json`: 1 files

## Operational Checks

```bash
ls -la tools/omega
find tools/omega -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files tools/omega | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
