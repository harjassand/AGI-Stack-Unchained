# scripts

> Path: `Extension-1/self_improve_code_v1/scripts`

## Mission

Extension layer modules for proposal, generation, and self-improvement capabilities.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `e2e_flagship_code_rsi_v1.sh`: shell automation script.

## File-Type Surface

- `sh`: 1 files

## Operational Checks

```bash
ls -la Extension-1/self_improve_code_v1/scripts
find Extension-1/self_improve_code_v1/scripts -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Extension-1/self_improve_code_v1/scripts | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
