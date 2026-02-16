from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from genesis.core.counterexamples import Counterexample
from genesis.shadow_cdel.baseline_registry import BaselineRegistry
from genesis.shadow_cdel.dataset_registry import DatasetRegistry
from genesis.shadow_cdel.lcb import hoeffding_lcb, hoeffding_ucb
from genesis.shadow_cdel.nontriviality import is_finite

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class ShadowCausalTrace:
    status: str
    failing_test: str | None
    counterexample: Any | None


@dataclass
class ShadowCausalResult:
    decision: str
    status: str
    metric_name: str | None
    metric_value: float | None
    bound: float | None
    threshold: float | None
    duration_ms: int
    sample_count: int
    forager_test_count: int
    nontriviality_pass: bool
    baseline_margin: float | None
    trace: ShadowCausalTrace | None


def _load_rows(path: Path) -> tuple[list[dict], dict]:
    rows = []
    meta: dict = {}
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if isinstance(row, dict) and "meta" in row:
                meta = row.get("meta") or {}
                continue
            rows.append(row)
    return rows, meta


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _diff_in_means(rows: list[dict], treatment: str, outcome: str) -> float | None:
    treated: list[float] = []
    control: list[float] = []
    for row in rows:
        tval = row.get(treatment)
        yval = row.get(outcome)
        if tval is None or yval is None:
            return None
        if int(tval) == 1:
            treated.append(float(yval))
        else:
            control.append(float(yval))
    if not treated or not control:
        return None
    mean_t = _mean(treated)
    mean_c = _mean(control)
    if mean_t is None or mean_c is None:
        return None
    return mean_t - mean_c


def _matrix_inverse(mat: list[list[float]]) -> list[list[float]] | None:
    n = len(mat)
    if n == 0:
        return None
    aug: list[list[float]] = []
    for i in range(n):
        row = [float(val) for val in mat[i]] + [0.0] * n
        row[n + i] = 1.0
        aug.append(row)
    for col in range(n):
        pivot = None
        for row in range(col, n):
            if abs(aug[row][col]) > 1e-12:
                pivot = row
                break
        if pivot is None:
            return None
        if pivot != col:
            aug[col], aug[pivot] = aug[pivot], aug[col]
        scale = aug[col][col]
        aug[col] = [val / scale for val in aug[col]]
        for row in range(n):
            if row == col:
                continue
            factor = aug[row][col]
            aug[row] = [a - factor * b for a, b in zip(aug[row], aug[col])]
    inv = [row[n:] for row in aug]
    return inv


def _ols_adjustment(rows: list[dict], treatment: str, outcome: str, covariates: list[str]) -> float | None:
    if not covariates:
        return _diff_in_means(rows, treatment, outcome)
    x_rows: list[list[float]] = []
    y_vals: list[float] = []
    for row in rows:
        tval = row.get(treatment)
        yval = row.get(outcome)
        cov = row.get("covariates") or {}
        if tval is None or yval is None or not isinstance(cov, dict):
            return None
        x_row = [1.0, float(tval)]
        for name in covariates:
            x_row.append(float(cov.get(name, 0.0)))
        x_rows.append(x_row)
        y_vals.append(float(yval))
    if not x_rows:
        return None
    k = len(x_rows[0])
    xtx = [[0.0 for _ in range(k)] for _ in range(k)]
    xty = [0.0 for _ in range(k)]
    for row, yval in zip(x_rows, y_vals):
        for i in range(k):
            xty[i] += row[i] * yval
            for j in range(k):
                xtx[i][j] += row[i] * row[j]
    inv = _matrix_inverse(xtx)
    if inv is None:
        return None
    beta = []
    for i in range(k):
        beta.append(sum(inv[i][j] * xty[j] for j in range(k)))
    return beta[1] if len(beta) > 1 else None


def _estimate_ate(rows: list[dict], spec: dict) -> float | None:
    estimator = spec.get("estimator", "diff_in_means")
    treatment = spec.get("treatment", "treatment")
    outcome = spec.get("outcome", "outcome")
    covariates = spec.get("covariates") or []
    covariates = [str(name) for name in covariates]
    if estimator == "ols_adjustment":
        return _ols_adjustment(rows, treatment, outcome, covariates)
    return _diff_in_means(rows, treatment, outcome)


def evaluate_shadow_causal(
    capsule: dict,
    seed: str = "0",
    margin: float = 0.0,
    counterexamples: list[Counterexample] | None = None,
    dataset_config_path: Path | None = None,
    dataset_id: str | None = None,
    forager_max_tests: int = 0,
) -> ShadowCausalResult:
    start = time.time()
    counterexamples = counterexamples or []

    if capsule.get("artifact_type") != "CAUSAL_MODEL":
        trace = ShadowCausalTrace(status="VIOLATION", failing_test=None, counterexample=None)
        return ShadowCausalResult("FAIL", "VIOLATION", None, None, None, None, 0, 0, 0, False, None, trace)

    causal_spec = capsule.get("x-causal") or {}
    if causal_spec.get("estimator") not in {"diff_in_means", "ols_adjustment"}:
        trace = ShadowCausalTrace(status="VIOLATION", failing_test=None, counterexample=None)
        return ShadowCausalResult("FAIL", "VIOLATION", None, None, None, None, 0, 0, 0, False, None, trace)

    dataset_path = dataset_config_path or (ROOT / "configs" / "datasets.json")
    registry = DatasetRegistry(dataset_path)
    dataset_key = dataset_id or "shadow_causal"
    handle = registry.resolve(dataset_key)
    if handle is None:
        trace = ShadowCausalTrace(status="VIOLATION", failing_test=None, counterexample=None)
        return ShadowCausalResult("FAIL", "VIOLATION", None, None, None, None, 0, 0, 0, False, None, trace)

    rows, meta = _load_rows(handle.path)
    metric_clause = (capsule.get("contract", {}).get("statistical_spec", {}).get("metrics") or [{}])[0]
    metric_name = metric_clause.get("name")
    if not metric_name:
        trace = ShadowCausalTrace(status="VIOLATION", failing_test=None, counterexample=None)
        return ShadowCausalResult("FAIL", "VIOLATION", None, None, None, None, 0, 0, 0, False, None, trace)

    true_ate = meta.get("true_ate")
    if true_ate is None:
        trace = ShadowCausalTrace(status="VIOLATION", failing_test=None, counterexample=None)
        return ShadowCausalResult("FAIL", "VIOLATION", None, None, None, None, 0, 0, 0, False, None, trace)
    try:
        true_ate_val = float(true_ate)
    except Exception:
        trace = ShadowCausalTrace(status="VIOLATION", failing_test=None, counterexample=None)
        return ShadowCausalResult("FAIL", "VIOLATION", None, None, None, None, 0, 0, 0, False, None, trace)

    estimate = _estimate_ate(rows, causal_spec)
    if estimate is None:
        trace = ShadowCausalTrace(status="VIOLATION", failing_test=None, counterexample=None)
        return ShadowCausalResult("FAIL", "VIOLATION", None, None, None, None, 0, 0, 0, False, None, trace)

    metric_value = abs(float(estimate) - true_ate_val)
    if metric_value < 0.0:
        metric_value = 0.0
    if metric_value > 1.0:
        metric_value = 1.0

    delta = (capsule.get("contract", {}).get("statistical_spec", {}).get("confidence_requirement") or {}).get(
        "delta", 0.01
    )
    try:
        delta = float(delta)
    except Exception:
        delta = 0.01
    direction = metric_clause.get("direction", "minimize")
    threshold = float(metric_clause.get("target", 0))
    n = len(rows)

    if direction == "minimize":
        ucb = hoeffding_ucb(metric_value, n, delta)
        decision = "PASS" if ucb.bound <= threshold - margin else "FAIL"
        bound = ucb.bound
    else:
        lcb = hoeffding_lcb(metric_value, n, delta)
        decision = "PASS" if lcb.bound >= threshold + margin else "FAIL"
        bound = lcb.bound

    baseline_margin = None
    baseline_pass = False
    registry = BaselineRegistry()
    baseline = registry.get("CAUSAL_MODEL", metric_name)
    if baseline is not None:
        if direction == "minimize":
            baseline_margin = baseline.value - metric_value
        else:
            baseline_margin = metric_value - baseline.value
        baseline_pass = baseline_margin >= baseline.min_margin

    nontriviality_pass = is_finite(metric_value) and baseline_pass
    if decision == "PASS" and not nontriviality_pass:
        decision = "FAIL"

    forager_count = 0
    if forager_max_tests > 0 and counterexamples:
        forager_count = min(forager_max_tests, len(counterexamples))

    trace = None
    status = "OK" if decision == "PASS" else "FAIL"
    if decision == "FAIL":
        failure_class = "NONTRIVIALITY" if not nontriviality_pass else "STAT_FAIL"
        trace = ShadowCausalTrace(
            status=failure_class,
            failing_test="metric_threshold",
            counterexample={
                "metric": metric_name,
                "value": metric_value,
                "bound": bound,
                "threshold": threshold,
            },
        )

    duration_ms = int((time.time() - start) * 1000)
    return ShadowCausalResult(
        decision,
        status,
        metric_name,
        metric_value,
        bound,
        threshold,
        duration_ms,
        n,
        forager_count,
        nontriviality_pass,
        baseline_margin,
        trace,
    )
