# test_vectors

> Path: `Genesis/extensions/code_patch_v1/test_vectors`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `candidate_minimal.json`: JSON contract, config, or artifact.
- `expected_hashes.json`: JSON contract, config, or artifact.
- `patch_minimal.diff`: project artifact.
- `policy_default.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 3 files
- `diff`: 1 files

## Operational Checks

```bash
ls -la Genesis/extensions/code_patch_v1/test_vectors
find Genesis/extensions/code_patch_v1/test_vectors -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/extensions/code_patch_v1/test_vectors | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
