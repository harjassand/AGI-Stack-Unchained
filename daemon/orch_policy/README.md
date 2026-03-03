# Orchestrator Policy Store

Policy artifacts used by orchestrator world-model selection and transition learning.

## Key Artifacts

- `orch_policy_bundle_v1.json`: Bundle descriptor binding policy table, train config, and dataset manifest.
- `orch_policy_table_v1.json`: Ranked capability actions by context key.
- `orch_transition_dataset_build_receipt_v1.json`: Dataset build provenance.
- `transition_events.jsonl`: Transition events consumed by dataset/build steps.

## Subdirectories

- `active/`: Active policy pointers/state.
- `eval_cache/`: Evaluation cache material.
- `store/manifests/`: Hash-addressed manifests for policy bundles and dataset manifests.

## Contract Notes

- `schema_version` fields are required and must match consumer expectations.
- Manifest filenames are hash-addressed and should be immutable after creation.
- Policy bundle IDs and referenced relpaths form replay-critical evidence.

## Inspection

```bash
cat daemon/orch_policy/orch_policy_bundle_v1.json
cat daemon/orch_policy/orch_policy_table_v1.json
```
