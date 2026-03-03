# v8_0

> Path: `Genesis/schema/v8_0`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `boundless_math_ignition_receipt_v1.jsonschema`: JSON Schema contract.
- `math_attempt_receipt_v1.jsonschema`: JSON Schema contract.
- `math_attempt_record_v1.jsonschema`: JSON Schema contract.
- `math_problem_spec_v1.jsonschema`: JSON Schema contract.
- `math_proof_artifact_v1.jsonschema`: JSON Schema contract.
- `math_research_ledger_v1.jsonl.schema`: project artifact.
- `math_solution_receipt_v1.jsonschema`: JSON Schema contract.
- `math_solved_index_v1.jsonschema`: JSON Schema contract.
- `math_toolchain_manifest_v1.jsonschema`: JSON Schema contract.
- `rsi_boundless_math_pack_v1.jsonschema`: JSON Schema contract.
- `rsi_daemon_pack_v8.jsonschema`: JSON Schema contract.

## File-Type Surface

- `jsonschema`: 10 files
- `schema`: 1 files

## Operational Checks

```bash
ls -la Genesis/schema/v8_0
find Genesis/schema/v8_0 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/schema/v8_0 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
