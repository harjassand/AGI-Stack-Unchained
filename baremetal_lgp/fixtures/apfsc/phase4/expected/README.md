# expected

> Path: `baremetal_lgp/fixtures/apfsc/phase4/expected`

## Mission

Bare-metal Rust runtime components, services, and performance-critical execution surfaces.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `phase4_arch_promotion_receipt.json`: JSON contract, config, or artifact.
- `phase4_formal_receipt.json`: JSON contract, config, or artifact.
- `phase4_searchlaw_ab_receipt.json`: JSON contract, config, or artifact.
- `phase4_searchlaw_offline_receipt.json`: JSON contract, config, or artifact.
- `phase4_searchlaw_promotion_receipt.json`: JSON contract, config, or artifact.
- `phase4_tool_shadow_receipt.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 6 files

## Operational Checks

```bash
ls -la baremetal_lgp/fixtures/apfsc/phase4/expected
find baremetal_lgp/fixtures/apfsc/phase4/expected -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files baremetal_lgp/fixtures/apfsc/phase4/expected | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
