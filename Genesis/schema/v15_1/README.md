# v15_1

> Path: `Genesis/schema/v15_1`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `brain_context_v1.jsonschema`: JSON Schema contract.
- `brain_corpus_suitepack_v1.jsonschema`: JSON Schema contract.
- `brain_decision_v1.jsonschema`: JSON Schema contract.
- `brain_perf_case_v1.jsonschema`: JSON Schema contract.
- `brain_suite_report_v1.jsonschema`: JSON Schema contract.
- `branch_coverage_report_v1.jsonschema`: JSON Schema contract.
- `kernel_brain_perf_report_v1.jsonschema`: JSON Schema contract.
- `toolchain_manifest_v15.jsonschema`: JSON Schema contract.

## File-Type Surface

- `jsonschema`: 8 files

## Operational Checks

```bash
ls -la Genesis/schema/v15_1
find Genesis/schema/v15_1 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/schema/v15_1 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
