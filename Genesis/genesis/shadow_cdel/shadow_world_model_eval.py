from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List

from genesis.core.counterexamples import Counterexample
from genesis.shadow_cdel.baseline_registry import BaselineRegistry
from genesis.shadow_cdel.dataset_registry import DatasetRegistry
from genesis.shadow_cdel.lcb import hoeffding_lcb, hoeffding_ucb
from genesis.shadow_cdel.nontriviality import MIN_OUTPUT_VARIANCE, is_finite, output_variance

ROOT = Path(__file__).resolve().parents[1]

@dataclass
class ShadowWorldModelTrace:
    status: str
    failing_test: str | None
    counterexample: Any | None


@dataclass
class ShadowWorldModelResult:
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
    trace: ShadowWorldModelTrace | None


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def _predict(model_spec: dict, features: List[float]) -> float:
    weights = model_spec.get("weights") or []
    bias = float(model_spec.get("bias", 0.0))
    score = sum(float(w) * float(x) for w, x in zip(weights, features)) + bias
    if model_spec.get("model_family") == "logistic_regression":
        return _sigmoid(score)
    return float(score)


def _metric_from_rows(model_spec: dict, rows: list[dict], metric_name: str) -> tuple[float, int, list[float]]:
    total = 0
    correct = 0
    mse_sum = 0.0
    preds: list[float] = []
    for row in rows:
        features = row.get("features")
        label = row.get("label")
        if not isinstance(features, list) or label is None:
            continue
        pred = _predict(model_spec, features)
        preds.append(pred)
        pred_label = 1 if pred >= 0.5 else 0
        total += 1
        mse_sum += (pred - float(label)) ** 2
        if pred_label == int(label):
            correct += 1
    if total <= 0:
        return 0.0, 0, preds
    if "accuracy" in metric_name:
        return correct / total, total, preds
    mse = mse_sum / total
    if mse < 0.0:
        mse = 0.0
    if mse > 1.0:
        mse = 1.0
    return mse, total, preds


def _load_rows(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _generate_forager_rows(
    rows: list[dict],
    counterexamples: list[Counterexample],
    max_tests: int,
) -> list[dict]:
    tests: list[dict] = []
    for row in rows[: max_tests]:
        features = row.get("features")
        if not isinstance(features, list):
            continue
        flipped = [float(x) * -1.0 for x in features]
        tests.append({"features": flipped, "label": row.get("label"), "group": row.get("group")})
        zeros = [0.0 for _ in features]
        tests.append({"features": zeros, "label": row.get("label"), "group": row.get("group")})
        scaled = [float(x) * 1000.0 for x in features]
        tests.append({"features": scaled, "label": row.get("label"), "group": row.get("group")})
        if len(tests) >= max_tests:
            break
    for entry in counterexamples:
        if len(tests) >= max_tests:
            break
        if isinstance(entry.input_value, dict):
            tests.append(entry.input_value)
    return tests[:max_tests]


def evaluate_shadow_world_model(
    capsule: dict,
    seed: str = "0",
    margin: float = 0.0,
    counterexamples: list[Counterexample] | None = None,
    dataset_config_path: Path | None = None,
    dataset_id: str | None = None,
    forager_max_tests: int = 0,
) -> ShadowWorldModelResult:
    start = time.time()
    counterexamples = counterexamples or []

    if capsule.get("artifact_type") != "WORLD_MODEL":
        trace = ShadowWorldModelTrace(status="VIOLATION", failing_test=None, counterexample=None)
        return ShadowWorldModelResult("FAIL", "VIOLATION", None, None, None, None, 0, 0, 0, False, None, trace)

    model_spec = capsule.get("x-world-model") or {}
    if model_spec.get("model_family") not in {"linear_regression", "logistic_regression"}:
        trace = ShadowWorldModelTrace(status="VIOLATION", failing_test=None, counterexample=None)
        return ShadowWorldModelResult("FAIL", "VIOLATION", None, None, None, None, 0, 0, 0, False, None, trace)

    dataset_path = dataset_config_path or (ROOT / "configs" / "datasets.json")
    registry = DatasetRegistry(dataset_path)
    dataset_key = dataset_id or "shadow_world_model"
    handle = registry.resolve(dataset_key)
    if handle is None:
        trace = ShadowWorldModelTrace(status="VIOLATION", failing_test=None, counterexample=None)
        return ShadowWorldModelResult("FAIL", "VIOLATION", None, None, None, None, 0, 0, 0, False, None, trace)

    rows = _load_rows(handle.path)
    metric_clause = (capsule.get("contract", {}).get("statistical_spec", {}).get("metrics") or [{}])[0]
    metric_name = metric_clause.get("name")
    if not metric_name:
        trace = ShadowWorldModelTrace(status="VIOLATION", failing_test=None, counterexample=None)
        return ShadowWorldModelResult("FAIL", "VIOLATION", None, None, None, None, 0, 0, 0, False, None, trace)

    metric_value, n, preds = _metric_from_rows(model_spec, rows, metric_name)
    delta = (capsule.get("contract", {}).get("statistical_spec", {}).get("confidence_requirement") or {}).get(
        "delta", 0.01
    )
    try:
        delta = float(delta)
    except Exception:
        delta = 0.01
    direction = metric_clause.get("direction", "maximize")
    threshold = float(metric_clause.get("target", 0))

    if direction == "maximize":
        lcb = hoeffding_lcb(metric_value, n, delta)
        decision = "PASS" if lcb.bound >= threshold + margin else "FAIL"
        bound = lcb.bound
    else:
        ucb = hoeffding_ucb(metric_value, n, delta)
        decision = "PASS" if ucb.bound <= threshold - margin else "FAIL"
        bound = ucb.bound

    baseline_margin = None
    baseline_pass = False
    registry = BaselineRegistry()
    baseline = registry.get("WORLD_MODEL", metric_name)
    if baseline is not None:
        if direction == "minimize":
            baseline_margin = baseline.value - metric_value
        else:
            baseline_margin = metric_value - baseline.value
        baseline_pass = baseline_margin >= baseline.min_margin

    variance = output_variance(preds)
    nonfinite = (not is_finite(metric_value)) or any(not is_finite(val) for val in preds)
    variance_pass = variance >= MIN_OUTPUT_VARIANCE
    nontriviality_pass = (not nonfinite) and variance_pass and baseline_pass
    if decision == "PASS" and not nontriviality_pass:
        decision = "FAIL"

    forager_count = 0
    if decision == "PASS" and forager_max_tests > 0:
        tests = _generate_forager_rows(rows, counterexamples, forager_max_tests)
        forager_count = len(tests)
        if tests:
            test_metric, _, _ = _metric_from_rows(model_spec, tests, metric_name)
            if direction == "maximize" and test_metric < threshold + margin:
                trace = ShadowWorldModelTrace(
                    status="TEST_FAIL",
                    failing_test="forager_metric",
                    counterexample=tests[0],
                )
                duration_ms = int((time.time() - start) * 1000)
                return ShadowWorldModelResult(
                    "FAIL",
                    "TEST_FAIL",
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
            if direction == "minimize" and test_metric > threshold - margin:
                trace = ShadowWorldModelTrace(
                    status="TEST_FAIL",
                    failing_test="forager_metric",
                    counterexample=tests[0],
                )
                duration_ms = int((time.time() - start) * 1000)
                return ShadowWorldModelResult(
                    "FAIL",
                    "TEST_FAIL",
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

    duration_ms = int((time.time() - start) * 1000)
    if not nontriviality_pass:
        failing = "nontriviality"
        if nonfinite:
            failing = "nontriviality:nonfinite"
        elif not variance_pass:
            failing = "nontriviality:variance"
        elif not baseline_pass:
            failing = "nontriviality:baseline"
        trace = ShadowWorldModelTrace(status="TEST_FAIL", failing_test=failing, counterexample=None)
        return ShadowWorldModelResult(
            "FAIL",
            "TEST_FAIL",
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

    if decision == "PASS":
        return ShadowWorldModelResult(
            "PASS",
            "OK",
            metric_name,
            metric_value,
            bound,
            threshold,
            duration_ms,
            n,
            forager_count,
            nontriviality_pass,
            baseline_margin,
            None,
        )

    trace = ShadowWorldModelTrace(
        status="TEST_FAIL",
        failing_test="metric_threshold",
        counterexample={"metric": metric_value, "threshold": threshold},
    )
    return ShadowWorldModelResult(
        "FAIL",
        "TEST_FAIL",
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
