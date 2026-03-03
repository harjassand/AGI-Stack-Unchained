# mission_control

> Path: `tools/mission_control/mission_control`

## Mission

Operational and developer tooling used across stack build, run, and validation workflows.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `static/`: component subtree.

## Key Files

- `__init__.py`: Python module or executable script.
- `__main__.py`: Python module or executable script.
- `omega_v4_0.py`: Python module or executable script.
- `run_scan.py`: Python module or executable script.
- `sas_val_v17_0.py`: Python module or executable script.
- `security.py`: Python module or executable script.
- `server.py`: Python module or executable script.

## File-Type Surface

- `py`: 7 files

## Operational Checks

```bash
ls -la tools/mission_control/mission_control
find tools/mission_control/mission_control -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files tools/mission_control/mission_control | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
