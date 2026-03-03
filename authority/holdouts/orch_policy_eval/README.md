# orch_policy_eval

> Path: `authority/holdouts/orch_policy_eval`

## Mission

Governance, authority pins, holdouts, and policy envelopes that gate promotion.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `.gitkeep`: project artifact.
- `sha256_656c74c3d0a166c4ea8361a91c51a22caa5d6f1fe5932d0707682ef50f098629.orch_policy_eval_config_v1.json`: JSON contract, config, or artifact.
- `sha256_a3be90d158d17da13e98d07cbc7ea499e087050c9add1bba83987cc60b73a5af.orch_transition_dataset_v1.jsonl`: project artifact.

## File-Type Surface

- `jsonl`: 1 files
- `json`: 1 files
- `gitkeep`: 1 files

## Operational Checks

```bash
ls -la authority/holdouts/orch_policy_eval
find authority/holdouts/orch_policy_eval -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files authority/holdouts/orch_policy_eval | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
