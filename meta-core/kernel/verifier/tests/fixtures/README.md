# fixtures

> Path: `meta-core/kernel/verifier/tests/fixtures`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `invalid_bundle_dominance_missing_condextra_inputs/`: component subtree.
- `invalid_bundle_no_safe/`: component subtree.
- `invalid_bundle_schema/`: component subtree.
- `invalid_bundle_tamper/`: component subtree.
- `parent_bundle/`: component subtree.
- `valid_bundle/`: component subtree.
- `valid_bundle_safe_three/`: component subtree.

## Key Files

- `state_edge.json`: JSON contract, config, or artifact.
- `state_small.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 2 files

## Operational Checks

```bash
ls -la meta-core/kernel/verifier/tests/fixtures
find meta-core/kernel/verifier/tests/fixtures -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files meta-core/kernel/verifier/tests/fixtures | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
