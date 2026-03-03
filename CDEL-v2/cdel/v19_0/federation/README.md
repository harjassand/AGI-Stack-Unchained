# federation

> Path: `CDEL-v2/cdel/v19_0/federation`

## Mission

Core verifier/runtime implementation for CDEL protocol versions and shared primitives.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `pins/`: component subtree.

## Key Files

- `__init__.py`: Python module or executable script.
- `check_ok_overlap_signature_v1.py`: Python module or executable script.
- `check_refutation_interop_v1.py`: Python module or executable script.
- `check_treaty_coherence_v1.py`: Python module or executable script.
- `check_treaty_v1.py`: Python module or executable script.
- `ok_ican_v1.py`: Python module or executable script.
- `portability_protocol_v1.py`: Python module or executable script.

## File-Type Surface

- `py`: 7 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v19_0/federation
find CDEL-v2/cdel/v19_0/federation -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v19_0/federation | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
