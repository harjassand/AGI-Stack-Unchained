# skills

> Path: `CDEL-v2/cdel/v18_0/skills`

## Mission

Core verifier/runtime implementation for CDEL protocol versions and shared primitives.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `__init__.py`: Python module or executable script.
- `eff_flywheel_v2_0_adapter_v1.py`: Python module or executable script.
- `ontology_v2_v1_6r_adapter_v1.py`: Python module or executable script.
- `persistence_v6_adapter_v1.py`: Python module or executable script.
- `skill_runner_v1.py`: Python module or executable script.
- `thermo_v5_adapter_v1.py`: Python module or executable script.
- `transfer_v1_6r_adapter_v1.py`: Python module or executable script.

## File-Type Surface

- `py`: 7 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v18_0/skills
find CDEL-v2/cdel/v18_0/skills -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v18_0/skills | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
