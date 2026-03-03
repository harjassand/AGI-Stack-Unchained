# rsi_epistemic_reduce_v1

> Path: `campaigns/rsi_epistemic_reduce_v1`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `epistemic_cert_profile_v1.json`: JSON contract, config, or artifact.
- `epistemic_confidence_calibration_v1.json`: JSON contract, config, or artifact.
- `epistemic_instruction_strip_contract_v1.json`: JSON contract, config, or artifact.
- `epistemic_kernel_spec_v1.json`: JSON contract, config, or artifact.
- `epistemic_reduce_contract_v1.json`: JSON contract, config, or artifact.
- `epistemic_retention_policy_v1.json`: JSON contract, config, or artifact.
- `epistemic_type_registry_v1.json`: JSON contract, config, or artifact.
- `rsi_epistemic_reduce_pack_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 8 files

## Operational Checks

```bash
ls -la campaigns/rsi_epistemic_reduce_v1
find campaigns/rsi_epistemic_reduce_v1 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_epistemic_reduce_v1 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
