# Run Artifact Contract

A run directory is **valid** if it contains:

- `config.json`
- `STATUS.json`
- `metrics.csv` (at least a header)
- `report.ndjson` (may be empty but must exist)
- and one of:
  - `DONE` (complete)
  - `FAILED.json` (failed)
  - neither (incomplete/running)

Research runs additionally include:

- `RUN_META.json` (non-semantic metadata for provenance)

## STATUS.json schema (minimum)

Required fields:

- `run_id` (string)
- `status` (`"running" | "complete" | "failed"`)
- `config_hash` (hex string)
- `tasks_hash` (hex string)
- `last_completed_task_index` (int)
- `last_completed_task_id` (string or null)
- `head_hash` (string or null)
- `counts` (object with `accepted`, `rejected` integers)

Optional fields:

- `started_at`, `updated_at` (timestamps)
- `seed`

## Resume Preconditions

A run is resumable only if:

- `STATUS.json` exists and `status` is not `complete`.
- `config_hash` matches the current config.json hash.
- `tasks_hash` matches the tasks file bytes hash.
- current ledger head equals `STATUS.json` `head_hash`.

A run **without** `STATUS.json` is **legacy** and must never be resumed.

## Claim Evaluation Rules

- If `DONE` is missing, the run is treated as **incomplete**.
- Required claims that depend on incomplete runs **fail**.
- Non-required claims may be reported but are not used to fail the suite.

## RUN_META.json

`RUN_META.json` captures non-semantic provenance (git commit, python/platform, timestamps, command args).
Validation may require it for research runs but does not affect semantics or hashing.

## Completion Markers

- `DONE` contents must match `STATUS.json.head_hash`.
- For failed runs, `FAILED.json` must exist with error details.
