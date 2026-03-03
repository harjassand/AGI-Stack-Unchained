# orch_worldmodel

> Path: `tools/orch_worldmodel`

## Mission

Operational and developer tooling used across stack build, run, and validation workflows.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `active_inference_driver_v1.py`: Python module or executable script.
- `campaign_orch_policy_trainer_v1.py`: Python module or executable script.
- `orch_transition_dataset_builder_v1.py`: Python module or executable script.
- `orch_worldmodel_math_q32_v1.py`: Python module or executable script.
- `orch_worldmodel_trainer_v1.py`: Python module or executable script.
- `pack_orch_policy_bundle_v1.py`: Python module or executable script.
- `query_router_rules_v1.json`: JSON contract, config, or artifact.
- `query_router_v1.py`: Python module or executable script.
- `uncertainty_report_v1.py`: Python module or executable script.

## File-Type Surface

- `py`: 8 files
- `json`: 1 files

## Operational Checks

```bash
ls -la tools/orch_worldmodel
find tools/orch_worldmodel -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files tools/orch_worldmodel | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
