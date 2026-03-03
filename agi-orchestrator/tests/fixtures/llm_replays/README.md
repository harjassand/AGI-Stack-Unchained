# llm_replays

> Path: `agi-orchestrator/tests/fixtures/llm_replays`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `io_algorithms_v1_replay.jsonl`: project artifact.

## File-Type Surface

- `jsonl`: 1 files

## Operational Checks

```bash
ls -la agi-orchestrator/tests/fixtures/llm_replays
find agi-orchestrator/tests/fixtures/llm_replays -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files agi-orchestrator/tests/fixtures/llm_replays | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
