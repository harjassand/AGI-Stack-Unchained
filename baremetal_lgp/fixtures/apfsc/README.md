# apfsc

> Path: `baremetal_lgp/fixtures/apfsc`

## Mission

Bare-metal Rust runtime components, services, and performance-critical execution surfaces.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `config/`: configuration contracts and defaults.
- `phase2/`: component subtree.
- `phase3/`: component subtree.
- `phase4/`: component subtree.
- `prior_seed/`: component subtree.
- `prod/`: component subtree.
- `reality_f0_det/`: component subtree.
- `reality_f1_text/`: component subtree.
- `substrate_seed/`: component subtree.

## Key Files

- No direct files at this level (directory primarily organizes subtrees).

## File-Type Surface

- No direct files to classify at this level.

## Operational Checks

```bash
ls -la baremetal_lgp/fixtures/apfsc
find baremetal_lgp/fixtures/apfsc -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files baremetal_lgp/fixtures/apfsc | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
