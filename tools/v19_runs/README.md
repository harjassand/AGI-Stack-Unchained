# v19_runs

> Path: `tools/v19_runs`

## Mission

Operational and developer tooling used across stack build, run, and validation workflows.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `extract_goal_synth_failing_cases_v1.py`: Python module or executable script.
- `ge_dispatch_evidence_v1.py`: Python module or executable script.
- `level_attainment_report_v1.py`: Python module or executable script.
- `omega_benchmark_gates_v19_v1.py`: Python module or executable script.
- `run_omega_v19_full_loop.py`: Python module or executable script.
- `v19_ladder_evidence_pipeline_v1.py`: Python module or executable script.

## File-Type Surface

- `py`: 6 files

## Operational Checks

```bash
ls -la tools/v19_runs
find tools/v19_runs -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files tools/v19_runs | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
