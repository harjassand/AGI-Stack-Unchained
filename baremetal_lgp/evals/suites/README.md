# suites

> Path: `baremetal_lgp/evals/suites`

## Mission

Bare-metal Rust runtime components, services, and performance-critical execution surfaces.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `phase1_regression.yaml`: YAML configuration or task spec.
- `phase2_constellation.yaml`: YAML configuration or task spec.
- `phase3_paradigm.yaml`: YAML configuration or task spec.
- `phase4_searchlaw.yaml`: YAML configuration or task spec.
- `prod_migration.yaml`: YAML configuration or task spec.
- `prod_perf.yaml`: YAML configuration or task spec.
- `prod_recovery.yaml`: YAML configuration or task spec.
- `prod_security.yaml`: YAML configuration or task spec.
- `prod_soak.yaml`: YAML configuration or task spec.

## File-Type Surface

- `yaml`: 9 files

## Operational Checks

```bash
ls -la baremetal_lgp/evals/suites
find baremetal_lgp/evals/suites -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files baremetal_lgp/evals/suites | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
