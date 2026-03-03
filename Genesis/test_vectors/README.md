# test_vectors

> Path: `Genesis/test_vectors`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `ccai_x_mind_v1/`: component subtree.
- `ccai_x_mind_v2/`: component subtree.
- `ccai_x_v1/`: component subtree.

## Key Files

- `capsule_minimal.hash.txt`: text output or trace artifact.
- `capsule_minimal.json`: JSON contract, config, or artifact.
- `receipt_minimal.hash.txt`: text output or trace artifact.
- `receipt_minimal.json`: JSON contract, config, or artifact.
- `transcript_minimal.hash.txt`: text output or trace artifact.
- `transcript_minimal.json`: JSON contract, config, or artifact.

## File-Type Surface

- `txt`: 3 files
- `json`: 3 files

## Operational Checks

```bash
ls -la Genesis/test_vectors
find Genesis/test_vectors -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/test_vectors | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
