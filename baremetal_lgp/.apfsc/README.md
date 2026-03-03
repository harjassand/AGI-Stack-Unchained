# .apfsc

> Path: `baremetal_lgp/.apfsc`

## Mission

Bare-metal Rust runtime components, services, and performance-critical execution surfaces.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `archive/`: component subtree.
- `banks/`: component subtree.
- `candidates/`: component subtree.
- `fixtures_snapshot/`: deterministic fixture data.
- `packs/`: component subtree.
- `pointers/`: component subtree.
- `protocol/`: component subtree.
- `queues/`: component subtree.
- `receipts/`: component subtree.
- `snapshots/`: component subtree.

## Key Files

- No direct files at this level (directory primarily organizes subtrees).

## File-Type Surface

- No direct files to classify at this level.

## Operational Checks

```bash
ls -la baremetal_lgp/.apfsc
find baremetal_lgp/.apfsc -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files baremetal_lgp/.apfsc | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
