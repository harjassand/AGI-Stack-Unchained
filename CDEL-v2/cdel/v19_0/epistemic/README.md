# epistemic

> Path: `CDEL-v2/cdel/v19_0/epistemic`

## Mission

Core verifier/runtime implementation for CDEL protocol versions and shared primitives.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `__init__.py`: Python module or executable script.
- `action_market_v1.py`: Python module or executable script.
- `capsule_v1.py`: Python module or executable script.
- `certs_v1.py`: Python module or executable script.
- `compaction_v1.py`: Python module or executable script.
- `instruction_strip_v1.py`: Python module or executable script.
- `reduce_v1.py`: Python module or executable script.
- `retention_v1.py`: Python module or executable script.
- `sip_adapter_stub_v1.py`: Python module or executable script.
- `type_registry_v1.py`: Python module or executable script.
- `usable_index_v1.py`: Python module or executable script.
- `verify_epistemic_capsule_v1.py`: Python module or executable script.
- `verify_epistemic_certs_v1.py`: Python module or executable script.
- `verify_epistemic_reduce_v1.py`: Python module or executable script.
- `verify_epistemic_type_governance_v1.py`: Python module or executable script.

## File-Type Surface

- `py`: 15 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v19_0/epistemic
find CDEL-v2/cdel/v19_0/epistemic -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v19_0/epistemic | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
