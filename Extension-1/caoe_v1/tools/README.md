# tools

> Path: `Extension-1/caoe_v1/tools`

## Mission

Extension layer modules for proposal, generation, and self-improvement capabilities.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `mdl_failure_witness_summary_v1_1.py`: Python module or executable script.
- `run_epoch_phase3_nuisance_v1_2.sh`: shell automation script.
- `solve_regime_oracle_depth2_v1.py`: Python module or executable script.
- `solve_regime_oracle_memoryless_v1.py`: Python module or executable script.
- `solve_regime_oracle_sequence_v1.py`: Python module or executable script.
- `verify_caoe_v1_1_proofpack.sh`: shell automation script.
- `verify_epoch_consistency_v1_1.py`: Python module or executable script.
- `verify_failure_witness_index_v1_1.py`: Python module or executable script.
- `verify_phase3_nuisance_v1_2.sh`: shell automation script.
- `verify_receipts_meta_core_v1.py`: Python module or executable script.

## File-Type Surface

- `py`: 7 files
- `sh`: 3 files

## Operational Checks

```bash
ls -la Extension-1/caoe_v1/tools
find Extension-1/caoe_v1/tools -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Extension-1/caoe_v1/tools | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
