# v1_5r

> Path: `Genesis/schema/v1_5r`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `benchmark_pack_v1.jsonschema`: JSON Schema contract.
- `epoch_commit_v1.jsonschema`: JSON Schema contract.
- `eval_budget_report_v1.jsonschema`: JSON Schema contract.
- `failure_witness_v1.jsonschema`: JSON Schema contract.
- `family_dsl_v1.jsonschema`: JSON Schema contract.
- `family_semantics_report_v1.jsonschema`: JSON Schema contract.
- `family_signature_v1.jsonschema`: JSON Schema contract.
- `frontier_v1.jsonschema`: JSON Schema contract.
- `macro_active_set_v1.jsonschema`: JSON Schema contract.
- `macro_def_v1.jsonschema`: JSON Schema contract.
- `macro_ledger_v1.jsonl.schema`: project artifact.
- `macro_mining_report_v1.jsonschema`: JSON Schema contract.
- `mech_patch_v1.jsonschema`: JSON Schema contract.
- `meta_benchmark_pack_v1.jsonschema`: JSON Schema contract.
- `meta_patch_admission_report_v1.jsonschema`: JSON Schema contract.
- `meta_patch_admit_receipt_v1.jsonschema`: JSON Schema contract.
- `meta_patch_proposal_v1.jsonschema`: JSON Schema contract.
- `meta_patch_v1.jsonschema`: JSON Schema contract.
- `rsi_integrity_receipt_v1.jsonschema`: JSON Schema contract.
- `rsi_integrity_window_report_v1.jsonschema`: JSON Schema contract.
- `rsi_portfolio_receipt_v1.jsonschema`: JSON Schema contract.
- `rsi_portfolio_window_report_v1.jsonschema`: JSON Schema contract.
- `rsi_real_campaign_pack_v1.jsonschema`: JSON Schema contract.
- `shrink_proof_v1.jsonschema`: JSON Schema contract.
- `trace_v1.jsonl.schema`: project artifact.
- ... and 2 more files.

## File-Type Surface

- `jsonschema`: 25 files
- `schema`: 2 files

## Operational Checks

```bash
ls -la Genesis/schema/v1_5r
find Genesis/schema/v1_5r -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/schema/v1_5r | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
