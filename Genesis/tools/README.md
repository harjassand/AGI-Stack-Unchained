# tools

> Path: `Genesis/tools`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `ccai_x_mind_v1/`: component subtree.
- `ccai_x_v1/`: component subtree.

## Key Files

- `canonicalize.py`: Python module or executable script.
- `canonicalize_ref.py`: Python module or executable script.
- `check_budget_strings.py`: Python module or executable script.
- `check_links.py`: Python module or executable script.
- `consistency_check.py`: Python module or executable script.
- `find_repo_root.py`: Python module or executable script.
- `mock_cdel.py`: Python module or executable script.
- `run_checks.sh`: shell automation script.
- `run_hardening_suite.sh`: shell automation script.
- `validate_json.sh`: shell automation script.
- `validate_receipt.py`: Python module or executable script.
- `validate_schema.py`: Python module or executable script.
- `verify_receipt.py`: Python module or executable script.

## File-Type Surface

- `py`: 10 files
- `sh`: 3 files

## Operational Checks

```bash
ls -la Genesis/tools
find Genesis/tools -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/tools | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
