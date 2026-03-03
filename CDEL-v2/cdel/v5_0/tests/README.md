# tests

> Path: `CDEL-v2/cdel/v5_0/tests`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `fixtures/`: deterministic fixture data.

## Key Files

- `__init__.py`: Python module or executable script.
- `test_v5_0_density_ratio_cross_multiply_exact.py`: Python module or executable script.
- `test_v5_0_powermetrics_parse_required_fields_fail_closed.py`: Python module or executable script.
- `test_v5_0_probe_receipt_hashes_match_raw_artifacts.py`: Python module or executable script.
- `test_v5_0_root_path_collision_fatal.py`: Python module or executable script.
- `test_v5_0_smoke_thermo_run_promotion_accepts_valid.py`: Python module or executable script.
- `test_v5_0_smoke_thermo_run_valid_no_promotion_rejected.py`: Python module or executable script.
- `test_v5_0_thermal_critical_aborts_invalid.py`: Python module or executable script.
- `test_v5_0_unbounded_stop_provenance_required.py`: Python module or executable script.

## File-Type Surface

- `py`: 9 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v5_0/tests
find CDEL-v2/cdel/v5_0/tests -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v5_0/tests | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
