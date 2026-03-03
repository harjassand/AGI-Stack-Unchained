# datasets

> Path: `Genesis/genesis/tests/fixtures/datasets`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `causal_shadow.jsonl`: project artifact.
- `shadow_eval.jsonl`: project artifact.
- `world_model_shadow.jsonl`: project artifact.

## File-Type Surface

- `jsonl`: 3 files

## Operational Checks

```bash
ls -la Genesis/genesis/tests/fixtures/datasets
find Genesis/genesis/tests/fixtures/datasets -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/genesis/tests/fixtures/datasets | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
