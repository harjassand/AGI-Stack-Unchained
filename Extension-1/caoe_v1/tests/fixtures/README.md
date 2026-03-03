# fixtures

> Path: `Extension-1/caoe_v1/tests/fixtures`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `anomaly_buffer_guided_order_v1_2.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 1 files

## Operational Checks

```bash
ls -la Extension-1/caoe_v1/tests/fixtures
find Extension-1/caoe_v1/tests/fixtures -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Extension-1/caoe_v1/tests/fixtures | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
