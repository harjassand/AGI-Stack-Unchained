# evals

> Path: `baremetal_lgp/evals`

## Mission

Bare-metal Rust runtime components, services, and performance-critical execution surfaces.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `baselines/`: component subtree.
- `reports/`: component subtree.
- `suites/`: component subtree.

## Key Files

- `registry.yaml`: YAML configuration or task spec.

## File-Type Surface

- `yaml`: 1 files

## Operational Checks

```bash
ls -la baremetal_lgp/evals
find baremetal_lgp/evals -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files baremetal_lgp/evals | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
