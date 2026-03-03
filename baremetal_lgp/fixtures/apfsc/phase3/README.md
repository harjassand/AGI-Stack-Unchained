# phase3

> Path: `baremetal_lgp/fixtures/apfsc/phase3`

## Mission

Bare-metal Rust runtime components, services, and performance-critical execution surfaces.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `config/`: configuration contracts and defaults.
- `expected/`: component subtree.
- `priors/`: component subtree.
- `reality_f4_event_sparse_base/`: component subtree.
- `reality_f4_event_sparse_robust/`: component subtree.
- `reality_f4_event_sparse_transfer/`: component subtree.
- `reality_f5_formal_alg_base/`: component subtree.
- `reality_f5_formal_alg_robust/`: component subtree.
- `reality_f5_formal_alg_transfer/`: component subtree.

## Key Files

- No direct files at this level (directory primarily organizes subtrees).

## File-Type Surface

- No direct files to classify at this level.

## Operational Checks

```bash
ls -la baremetal_lgp/fixtures/apfsc/phase3
find baremetal_lgp/fixtures/apfsc/phase3 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files baremetal_lgp/fixtures/apfsc/phase3 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
