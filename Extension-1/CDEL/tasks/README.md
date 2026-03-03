# tasks

> Path: `Extension-1/CDEL/tasks`

## Mission

Extension layer modules for proposal, generation, and self-improvement capabilities.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `__init__.py`: Python module or executable script.
- `distractors_100k.jsonl`: project artifact.
- `distractors_10k.jsonl`: project artifact.
- `distractors_1k.jsonl`: project artifact.
- `make_capacity_filler.py`: Python module or executable script.
- `make_curriculum.py`: Python module or executable script.
- `make_fragmentation.py`: Python module or executable script.
- `stream_1000.jsonl`: project artifact.
- `stream_1000_bounded.jsonl`: project artifact.
- `stream_1000_mixed.jsonl`: project artifact.
- `stream_1000_proofheavy.jsonl`: project artifact.
- `stream_1000_with_100k_before.jsonl`: project artifact.
- `stream_1000_with_10k_before.jsonl`: project artifact.
- `stream_1000_with_10k_interleave10.jsonl`: project artifact.
- `stream_200_bounded.jsonl`: project artifact.
- `stream_200_mixed.jsonl`: project artifact.
- `stream_200_proofheavy.jsonl`: project artifact.
- `stream_200_with_10k_before.jsonl`: project artifact.
- `stream_200_with_10k_interleave10.jsonl`: project artifact.
- `stream_200_with_1k_before.jsonl`: project artifact.
- `stream_200_with_1k_interleave5.jsonl`: project artifact.
- `stream_50_bounded.jsonl`: project artifact.
- `stream_50_mixed.jsonl`: project artifact.
- `stream_50_proofheavy.jsonl`: project artifact.
- `stream_50_with_1k_before.jsonl`: project artifact.
- ... and 3 more files.

## File-Type Surface

- `jsonl`: 24 files
- `py`: 4 files

## Operational Checks

```bash
ls -la Extension-1/CDEL/tasks
find Extension-1/CDEL/tasks -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Extension-1/CDEL/tasks | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
