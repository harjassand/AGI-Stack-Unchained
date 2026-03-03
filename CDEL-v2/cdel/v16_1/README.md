# v16_1

> Path: `CDEL-v2/cdel/v16_1`

## Mission

Core verifier/runtime implementation for CDEL protocol versions and shared primitives.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `rust/`: component subtree.
- `tests/`: tests and validation assets.
- `tests_sas_metasearch/`: tests and validation assets.

## Key Files

- `__init__.py`: Python module or executable script.
- `metasearch_build_rust_v1.py`: Python module or executable script.
- `metasearch_codegen_rust_v1.py`: Python module or executable script.
- `metasearch_corpus_v1.py`: Python module or executable script.
- `metasearch_policy_ir_v1.py`: Python module or executable script.
- `metasearch_prior_v1.py`: Python module or executable script.
- `metasearch_promotion_bundle_v2.py`: Python module or executable script.
- `metasearch_run_v1.py`: Python module or executable script.
- `metasearch_selection_v1.py`: Python module or executable script.
- `metasearch_state_snapshot_v1.py`: Python module or executable script.
- `metasearch_trace_v1.py`: Python module or executable script.
- `metasearch_trace_v2.py`: Python module or executable script.
- `verify_rsi_sas_metasearch_v1.py`: Python module or executable script.
- `verify_rsi_sas_metasearch_v16_1.py`: Python module or executable script.

## File-Type Surface

- `py`: 14 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v16_1
find CDEL-v2/cdel/v16_1 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v16_1 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
