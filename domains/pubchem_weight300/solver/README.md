# solver

> Path: `domains/pubchem_weight300/solver`

## Mission

Domain packs, schemas, and domain-specific solver scaffolding for polymath workflows.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `baseline_solver_v1.py`: Python module or executable script.

## File-Type Surface

- `py`: 1 files

## Operational Checks

```bash
ls -la domains/pubchem_weight300/solver
find domains/pubchem_weight300/solver -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files domains/pubchem_weight300/solver | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
