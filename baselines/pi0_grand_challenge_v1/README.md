# PI0 Grand Challenge Baseline v1

Reference baseline report for the `grand_challenge_heldout_v1` suite.

## Files

- `baseline_report_v1.json`: Canonical baseline artifact (`schema=baseline_report_v1`).

## What This Baseline Captures

- `baseline_id`: Logical identifier for the baseline release.
- `suite_id`: Heldout suite this baseline was measured against.
- `pass_rate_num` and `pass_rate_den`: Deterministic pass-rate numerator and denominator.
- `solved_task_ids` and `solved_task_ids_hash`: Solved-set evidence.
- `task_budget`: Compute and wall-time budget under which results were produced.

## Usage

```bash
cat baselines/pi0_grand_challenge_v1/baseline_report_v1.json
```

Use this report as a stable comparator when evaluating new runs on the same suite.
