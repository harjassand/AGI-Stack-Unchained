# core

> Path: `Genesis/genesis/core`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `__init__.py`: Python module or executable script.
- `archive.py`: Python module or executable script.
- `causal_search.py`: Python module or executable script.
- `codesign.py`: Python module or executable script.
- `component_store.py`: Python module or executable script.
- `counterexamples.py`: Python module or executable script.
- `distill.py`: Python module or executable script.
- `failure_patterns.py`: Python module or executable script.
- `library.py`: Python module or executable script.
- `operators.py`: Python module or executable script.
- `planning.py`: Python module or executable script.
- `policy_search.py`: Python module or executable script.
- `search_loop.py`: Python module or executable script.
- `world_model_search.py`: Python module or executable script.

## File-Type Surface

- `py`: 14 files

## Operational Checks

```bash
ls -la Genesis/genesis/core
find Genesis/genesis/core -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/genesis/core | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
