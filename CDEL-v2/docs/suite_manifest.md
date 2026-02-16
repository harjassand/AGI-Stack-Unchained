# Suite Manifest Schema

Suite manifests declare which claims a run suite intends to satisfy. They live at either:

- `<runs_root>/suite_manifest.json`, or
- `claims/suite_manifests/<suite_name>.json`

`check_claims.py` validates manifests and applies SKIP semantics when a suite is partial.

## Required fields

```
{
  "suite_name": "runs_full",
  "claim_complete": true,
  "claims": { ... }
}
```

- `suite_name` (string): name of the suite/run root.
- `claim_complete` (bool): true if the suite is intended to satisfy all claims; false if partial.
- `claims` (object): per-claim configuration overrides.

## Claim overrides

The `claims` object is keyed by claim id. Each claim config may include only the keys it needs.

Supported keys:

- `required` (bool)
- `audit_full_runs` (list of strings)
- `audit_fast_runs` (list of strings)
- `runs` (list of strings)
- `run` (string)
- `indexed_run` (string)
- `scan_run` (string)
- `bounded_run` (string)
- `proof_run` (string)
- `baseline_run` (string)
- `reuse_run` (string)
- `max_median_closure_ratio` (number)
- `max_closure_slope` (number)
- `min_scan_to_indexed_ratio` (number)
- `min_capacity_reject_ratio` (number)
- `min_proof_total_nodes` (number)
- `min_proof_reject_ratio` (number)
- `min_reuse_rate_delta` (number)
- `min_unused_fraction_delta` (number)
- `min_symbols_per_task_delta` (number)

If a suite is partial (`claim_complete: false`) and omits a claim id from `claims`,
`check_claims.py` records that claim as **SKIP** instead of FAIL.
