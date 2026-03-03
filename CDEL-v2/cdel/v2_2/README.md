# v2_2

> Path: `CDEL-v2/cdel/v2_2`

## Mission

Core verifier/runtime implementation for CDEL protocol versions and shared primitives.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `tests/`: tests and validation assets.

## Key Files

- `__init__.py`: Python module or executable script.
- `autocodepatch.py`: Python module or executable script.
- `code_patch.py`: Python module or executable script.
- `constants.py`: Python module or executable script.
- `csi_bench.py`: Python module or executable script.
- `csi_meter.py`: Python module or executable script.
- `verify_rsi_csi_v1.py`: Python module or executable script.
- `verify_rsi_demon_v8.py`: Python module or executable script.

## File-Type Surface

- `py`: 8 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v2_2
find CDEL-v2/cdel/v2_2 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v2_2 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
