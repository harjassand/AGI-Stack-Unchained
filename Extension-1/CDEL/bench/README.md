# bench

> Path: `Extension-1/CDEL/bench`

## Mission

Extension layer modules for proposal, generation, and self-improvement capabilities.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `interleave_streams.py`: Python module or executable script.
- `make_distractors.py`: Python module or executable script.
- `scan_scaling.py`: Python module or executable script.

## File-Type Surface

- `py`: 3 files

## Operational Checks

```bash
ls -la Extension-1/CDEL/bench
find Extension-1/CDEL/bench -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Extension-1/CDEL/bench | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
