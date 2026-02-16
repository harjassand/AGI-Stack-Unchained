# CDEL Claims v1

This document defines the hypothesis claims as measurable predicates over run artifacts.

Claims:

- C1 Non-interference: `audit-full` passes for required runs; no definition hash drift.
- C2 Append-only: `audit-fast` passes for required runs; ledger replay reproduces head.
- C3 Addressability (sublinear load): for distractor runs, `median_closure_ratio` and `closure_vs_ledger_slope` remain below thresholds.
- C3-scan Baseline (optional): scan load mode shows significantly higher scanned_modules_count than indexed.
- C4 Capacity law: after exhaustion, CAPACITY_EXCEEDED dominates rejections beyond a threshold.
- C5 Certificate knob: proof-heavy runs show nonzero proof mass and proof-related rejections vs bounded runs.
- C6 Reuse/fragmentation control: enum_reuse yields higher reuse rate than baseline.
- C7 Cache equivalence (optional): cache on/off runs produce identical head hash and acceptance decisions.
- C8 Hygiene (optional): reuse/alias strategies reduce unused symbol fraction and symbols per accepted task.

Thresholds and required runs live in `claims/thresholds.json`.
