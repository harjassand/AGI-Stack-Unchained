# reality_f0_det_base

> Path: `baremetal_lgp/fixtures/apfsc/phase2/reality_f0_det_base`

## Mission

Bare-metal Rust runtime components, services, and performance-critical execution surfaces.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `manifest.json`: JSON contract, config, or artifact.
- `payload.bin`: project artifact.

## File-Type Surface

- `json`: 1 files
- `bin`: 1 files

## Operational Checks

```bash
ls -la baremetal_lgp/fixtures/apfsc/phase2/reality_f0_det_base
find baremetal_lgp/fixtures/apfsc/phase2/reality_f0_det_base -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files baremetal_lgp/fixtures/apfsc/phase2/reality_f0_det_base | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
