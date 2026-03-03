# scripts

> Path: `CDEL-v2/scripts`

## Mission

Local component subtree within the AGI stack; maintain deterministic, contract-safe changes.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `bootstrap_research_machine.sh`: shell automation script.
- `make_paper_bundle.sh`: shell automation script.
- `promote_candidate_dev_vs_heldout.py`: Python module or executable script.
- `repro_quickstart.sh`: shell automation script.
- `run_capacity_exhaustion.sh`: shell automation script.
- `run_flagships.sh`: shell automation script.
- `run_gates.sh`: shell automation script.
- `run_suite.sh`: shell automation script.
- `run_suite_mid.sh`: shell automation script.
- `run_suite_quick.sh`: shell automation script.
- `smoke_dev_vs_heldout_gate.sh`: shell automation script.
- `smoke_e2e.sh`: shell automation script.
- `smoke_env_harness_adopt.sh`: shell automation script.
- `smoke_evidence_suite.sh`: shell automation script.
- `smoke_generalization_experiment.sh`: shell automation script.
- `smoke_io_harness_adopt.sh`: shell automation script.
- `smoke_pyut_harness_adopt.sh`: shell automation script.
- `smoke_rebuild.sh`: shell automation script.
- `smoke_scaling_experiment.sh`: shell automation script.
- `smoke_solve_one_task.sh`: shell automation script.
- `smoke_solve_stress_small.sh`: shell automation script.
- `smoke_solve_suite_ablations_golden.sh`: shell automation script.
- `smoke_solve_suite_ablations_small.sh`: shell automation script.
- `smoke_solve_suite_small.sh`: shell automation script.
- `smoke_statcert_adopt.sh`: shell automation script.
- ... and 3 more files.

## File-Type Surface

- `sh`: 27 files
- `py`: 1 files

## Operational Checks

```bash
ls -la CDEL-v2/scripts
find CDEL-v2/scripts -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/scripts | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
