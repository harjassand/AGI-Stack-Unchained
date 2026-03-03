# dev_receipts

> Path: `smoking_gun_v11_0_2026-02-04/state/eval/dev_receipts`

## Mission

Evidence-pack artifacts and deterministic replay references for smoking-gun validation.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `sha256_56ea4bb025db1a1a87bff31b01915693f6df71e1627caf46006c655a9b734810.sas_model_eval_receipt_v1.json`: JSON contract, config, or artifact.
- `sha256_685355b027fde3785a8cd40757b4b1d21ac53de8d9427241d29c0d6d26cf3146.sas_model_eval_receipt_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 2 files

## Operational Checks

```bash
ls -la smoking_gun_v11_0_2026-02-04/state/eval/dev_receipts
find smoking_gun_v11_0_2026-02-04/state/eval/dev_receipts -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files smoking_gun_v11_0_2026-02-04/state/eval/dev_receipts | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
