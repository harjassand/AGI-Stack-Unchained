# tests

> Path: `CDEL-v2/cdel/v2_1/tests`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `__init__.py`: Python module or executable script.
- `test_autoconcept_manifest_hash_chain.py`: Python module or executable script.
- `test_opt_concept_safety_grid_monotone.py`: Python module or executable script.
- `test_opt_concept_schema_additional_properties_rejected.py`: Python module or executable script.
- `test_opt_dsl_call_order_acyclic.py`: Python module or executable script.
- `test_opt_dsl_eval_checked_overflow.py`: Python module or executable script.
- `test_recursive_ontology_transfer_gate_blocks.py`: Python module or executable script.
- `test_recursive_ontology_two_concepts_requires_call.py`: Python module or executable script.

## File-Type Surface

- `py`: 8 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v2_1/tests
find CDEL-v2/cdel/v2_1/tests -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v2_1/tests | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
