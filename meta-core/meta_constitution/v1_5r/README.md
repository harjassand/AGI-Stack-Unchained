# v1_5r

> Path: `meta-core/meta_constitution/v1_5r`

## Mission

Promotion, staging, verification, and rollback control-plane foundations.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `META_HASH`: project artifact.
- `build_meta_hash.sh`: shell automation script.
- `cmeta_equivalence_workvec_v1.md`: documentation artifact.
- `constants_v1.json`: JSON contract, config, or artifact.
- `ctime_admission_v1.md`: documentation artifact.
- `ctime_eviction_v1.md`: documentation artifact.
- `ecology_contract_v1.md`: documentation artifact.
- `failure_kind_mapping_v1.md`: documentation artifact.
- `family_dsl_semantics_v1.md`: documentation artifact.
- `frontier_compression_v1.md`: documentation artifact.
- `phi_core_v1.md`: documentation artifact.
- `pi0_baselines_v1.md`: documentation artifact.
- `pi0_programs_v1.json`: JSON contract, config, or artifact.
- `promotion_dominance_v1.md`: documentation artifact.
- `signature_distance_v1.md`: documentation artifact.

## File-Type Surface

- `md`: 11 files
- `json`: 2 files
- `sh`: 1 files
- `(no_ext)`: 1 files

## Operational Checks

```bash
ls -la meta-core/meta_constitution/v1_5r
find meta-core/meta_constitution/v1_5r -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files meta-core/meta_constitution/v1_5r | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
