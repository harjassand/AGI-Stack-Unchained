# promotion

> Path: `campaigns/rsi_sas_kernel_v15_0/fixtures/rsi_sas_system_v14_0/reference_state/promotion`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `sha256_6eceb40600d55ec4354cdb2842930f0972a80e6409ee998675f55a47870f43bf.sas_system_component_registry_v1.json`: JSON contract, config, or artifact.
- `sha256_704ded44a5d433027bb6095bfe45636f7eb8f61c044f202382524ed0fca712de.sas_system_promotion_bundle_v1.json`: JSON contract, config, or artifact.
- `sha256_c1f0deaf2e8440b5eba979d68197b91f3e1d4dd4f92cb24f4917e0e70f9a6aa0.sas_system_component_registry_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 3 files

## Operational Checks

```bash
ls -la campaigns/rsi_sas_kernel_v15_0/fixtures/rsi_sas_system_v14_0/reference_state/promotion
find campaigns/rsi_sas_kernel_v15_0/fixtures/rsi_sas_system_v14_0/reference_state/promotion -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_sas_kernel_v15_0/fixtures/rsi_sas_system_v14_0/reference_state/promotion | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
