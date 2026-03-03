# heldout_receipts

> Path: `smoking_gun_v11_0_2026-02-04/state/eval/heldout_receipts`

## Mission

Evidence-pack artifacts and deterministic replay references for smoking-gun validation.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `sha256_16aa6f69d18a7475ba362a6e52de6d5bc98eeef1509742eba03404197949ba42.sas_model_eval_receipt_heldout_v1.json`: JSON contract, config, or artifact.
- `sha256_95019ba98985c0cb0d3e002ab5cae5741432ef068876f6d2ceea6068bf46351f.sas_model_eval_receipt_heldout_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 2 files

## Operational Checks

```bash
ls -la smoking_gun_v11_0_2026-02-04/state/eval/heldout_receipts
find smoking_gun_v11_0_2026-02-04/state/eval/heldout_receipts -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files smoking_gun_v11_0_2026-02-04/state/eval/heldout_receipts | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
