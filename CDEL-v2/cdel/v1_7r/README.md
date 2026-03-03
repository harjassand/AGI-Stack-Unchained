# v1_7r

> Path: `CDEL-v2/cdel/v1_7r`

## Mission

Core verifier/runtime implementation for CDEL protocol versions and shared primitives.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `demon/`: component subtree.
- `envs/`: component subtree.
- `macros_v2/`: component subtree.
- `ontology_v3/`: component subtree.
- `science/`: component subtree.
- `science_mech/`: component subtree.
- `science_policy/`: component subtree.
- `tests/`: tests and validation assets.

## Key Files

- `__init__.py`: Python module or executable script.
- `canon.py`: Python module or executable script.
- `constants.py`: Python module or executable script.
- `hashutil.py`: Python module or executable script.
- `macro_cross_env_support_report_v2.py`: Python module or executable script.
- `rsi_science_tracker.py`: Python module or executable script.
- `run_rsi_campaign.py`: Python module or executable script.
- `run_rsi_science_campaign.py`: Python module or executable script.
- `verify_rsi_demon_v3.py`: Python module or executable script.
- `verify_rsi_science.py`: Python module or executable script.

## File-Type Surface

- `py`: 10 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v1_7r
find CDEL-v2/cdel/v1_7r -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v1_7r | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
