# tools

> Path: `Genesis/genesis/tools`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `archive_stats.py`: Python module or executable script.
- `path_utils.py`: Python module or executable script.
- `redteam_genesis.py`: Python module or executable script.
- `release_pack.py`: Python module or executable script.
- `release_registry.py`: Python module or executable script.
- `supersede_release.py`: Python module or executable script.
- `verify_release_pack.py`: Python module or executable script.
- `verify_specpack_lock.py`: Python module or executable script.

## File-Type Surface

- `py`: 8 files

## Operational Checks

```bash
ls -la Genesis/genesis/tools
find Genesis/genesis/tools -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/genesis/tools | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
