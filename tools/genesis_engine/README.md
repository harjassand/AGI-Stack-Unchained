# genesis_engine

> Path: `tools/genesis_engine`

## Mission

Operational and developer tooling used across stack build, run, and validation workflows.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `config/`: configuration contracts and defaults.
- `tests/`: tests and validation assets.

## Key Files

- `ge_audit_report_sh1_v0_1.py`: Python module or executable script.
- `ge_symbiotic_optimizer_v0_2.py`: Python module or executable script.
- `ge_symbiotic_optimizer_v0_3.py`: Python module or executable script.
- `sh1_behavior_sig_v1.py`: Python module or executable script.
- `sh1_pd_v1.py`: Python module or executable script.
- `sh1_xs_v1.py`: Python module or executable script.

## File-Type Surface

- `py`: 6 files

## Operational Checks

```bash
ls -la tools/genesis_engine
find tools/genesis_engine -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files tools/genesis_engine | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
