# tests_sas_metasearch

> Path: `CDEL-v2/cdel/v16_0/tests_sas_metasearch`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `__init__.py`: Python module or executable script.
- `conftest.py`: pytest shared fixtures and hooks.
- `test_build_reproducible.py`: Python module or executable script.
- `test_e2e_valid.py`: Python module or executable script.
- `test_efficiency_gate_50pct.py`: Python module or executable script.
- `test_foil_hooke_not_newton.py`: Python module or executable script.
- `test_forbidden_tokens_rust.py`: Python module or executable script.
- `test_no_holdout_leak.py`: Python module or executable script.
- `test_trace_corpus_dev_only.py`: Python module or executable script.
- `utils.py`: Python module or executable script.

## File-Type Surface

- `py`: 10 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v16_0/tests_sas_metasearch
find CDEL-v2/cdel/v16_0/tests_sas_metasearch -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v16_0/tests_sas_metasearch | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
