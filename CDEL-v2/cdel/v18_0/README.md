# v18_0

> Path: `CDEL-v2/cdel/v18_0`

## Mission

Core verifier/runtime implementation for CDEL protocol versions and shared primitives.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `authority/`: component subtree.
- `ccap/`: component subtree.
- `ek/`: component subtree.
- `eudrs_u/`: component subtree.
- `gir/`: component subtree.
- `op/`: component subtree.
- `realize/`: component subtree.
- `skills/`: component subtree.
- `tests_endurance/`: tests and validation assets.
- `tests_fast/`: tests and validation assets.
- `tests_integration/`: tests and validation assets.
- `tests_omega_daemon/`: tests and validation assets.

## Key Files

- `__init__.py`: Python module or executable script.
- `campaign_apply_shadow_proposal_v1.py`: Python module or executable script.
- `campaign_bid_market_toy_v1.py`: Python module or executable script.
- `campaign_ge_symbiotic_optimizer_sh1_v0_1.py`: Python module or executable script.
- `campaign_omega_native_module_v0_1.py`: Python module or executable script.
- `campaign_omega_skill_eff_flywheel_v1.py`: Python module or executable script.
- `campaign_omega_skill_ontology_v1.py`: Python module or executable script.
- `campaign_omega_skill_persistence_v1.py`: Python module or executable script.
- `campaign_omega_skill_thermo_v1.py`: Python module or executable script.
- `campaign_omega_skill_transfer_v1.py`: Python module or executable script.
- `campaign_phase0_victim_ccap_v0_1.py`: Python module or executable script.
- `campaign_polymath_bootstrap_domain_v1.py`: Python module or executable script.
- `campaign_polymath_conquer_domain_v1.py`: Python module or executable script.
- `campaign_polymath_scout_v1.py`: Python module or executable script.
- `campaign_polymath_sip_ingestion_l0_v1.py`: Python module or executable script.
- `campaign_rsi_knowledge_transpiler_v1.py`: Python module or executable script.
- `campaign_self_optimize_core_v1.py`: Python module or executable script.
- `ccap_budget_v1.py`: Python module or executable script.
- `ccap_runtime_v1.py`: Python module or executable script.
- `hard_task_suite_v1.py`: Python module or executable script.
- `omega_activator_v1.py`: Python module or executable script.
- `omega_allowlists_v1.py`: Python module or executable script.
- `omega_bid_market_v1.py`: Python module or executable script.
- `omega_budgets_v1.py`: Python module or executable script.
- `omega_common_v1.py`: Python module or executable script.
- ... and 39 more files.

## File-Type Surface

- `py`: 64 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v18_0
find CDEL-v2/cdel/v18_0 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v18_0 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
