# v2_2

> Path: `Genesis/schema/v2_2`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `code_patch_v1.jsonschema`: JSON Schema contract.
- `csi_bench_report_v1.jsonschema`: JSON Schema contract.
- `csi_bench_suite_v1.jsonschema`: JSON Schema contract.
- `csi_ledger_v1.jsonl.schema`: project artifact.
- `csi_manifest_v1.jsonschema`: JSON Schema contract.
- `csi_test_report_v1.jsonschema`: JSON Schema contract.
- `rsi_csi_receipt_v1.jsonschema`: JSON Schema contract.
- `rsi_csi_report_v1.jsonschema`: JSON Schema contract.
- `rsi_real_csi_pack_v1.jsonschema`: JSON Schema contract.
- `rsi_real_demon_campaign_pack_v8.jsonschema`: JSON Schema contract.

## File-Type Surface

- `jsonschema`: 9 files
- `schema`: 1 files

## Operational Checks

```bash
ls -la Genesis/schema/v2_2
find Genesis/schema/v2_2 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/schema/v2_2 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
