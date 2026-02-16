from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from genesis.core.counterexamples import Counterexample
from genesis.shadow_cdel.dataset_registry import DatasetRegistry
from genesis.shadow_cdel.forager import evaluate_tests, generate_tests
from genesis.shadow_cdel.lcb import hoeffding_lcb, hoeffding_ucb

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class ShadowTrace:
    status: str
    failing_test: str | None
    counterexample: Any | None


@dataclass
class ShadowResult:
    decision: str
    status: str
    metric_name: str | None
    metric_value: float | None
    bound: float | None
    threshold: float | None
    duration_ms: int
    tests_passed: int
    tests_total: int
    forager_test_count: int
    trace: ShadowTrace | None


@dataclass
class SandboxResult:
    exit_code: int
    stdout: bytes
    stderr: bytes
    timed_out: bool
    duration_ms: int


def _run_command(command: List[str], work_dir: Path, timeout_s: float, env: Dict[str, str]) -> SandboxResult:
    start = time.time()
    try:
        proc = subprocess.run(
            command,
            cwd=str(work_dir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_s,
            check=False,
        )
        timed_out = False
        stdout = proc.stdout or b""
        stderr = proc.stderr or b""
        exit_code = proc.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = exc.stdout or b""
        stderr = exc.stderr or b""
        exit_code = 124

    duration_ms = int((time.time() - start) * 1000)
    return SandboxResult(
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        duration_ms=duration_ms,
    )


def _parse_output(stdout: bytes) -> dict:
    text = stdout.decode("utf-8", errors="replace").strip()
    if not text:
        return {"metrics": {}, "tests": []}
    return json.loads(text)


def _determine_n(metrics: dict, resource_spec: dict) -> int:
    for key in ("sample_count", "n"):
        value = metrics.get(key)
        if isinstance(value, int) and value > 0:
            return value
        if isinstance(value, float) and value.is_integer() and value > 0:
            return int(value)
    n = int(resource_spec.get("max_sample_count", 0))
    return n if n > 0 else 0


def _runtime_hint_ms(resource_spec: dict) -> int:
    return int(resource_spec.get("max_wall_time_ms", 0))


def evaluate_shadow(
    capsule: dict,
    seed: str = "0",
    margin: float = 0.0,
    counterexamples: list[Counterexample] | None = None,
    dataset_config_path: Path | None = None,
    dataset_id: str | None = None,
    forager_max_tests: int = 0,
) -> ShadowResult:
    counterexamples = counterexamples or []
    forager_count = 0

    if capsule.get("artifact_type") != "ALGORITHM":
        trace = ShadowTrace(status="VIOLATION", failing_test=None, counterexample=None)
        return ShadowResult(
            decision="FAIL",
            status="VIOLATION",
            metric_name=None,
            metric_value=None,
            bound=None,
            threshold=None,
            duration_ms=0,
            tests_passed=0,
            tests_total=0,
            forager_test_count=forager_count,
            trace=trace,
        )

    harness = capsule.get("x-harness") or {}
    script = harness.get("script")
    if not isinstance(script, str) or not script:
        trace = ShadowTrace(status="VIOLATION", failing_test=None, counterexample=None)
        return ShadowResult("FAIL", "VIOLATION", None, None, None, None, 0, 0, 0, forager_count, trace)

    args = harness.get("args") or []
    if not isinstance(args, list):
        args = []

    resource_spec = capsule.get("contract", {}).get("resource_spec", {})
    runtime_hint = _runtime_hint_ms(resource_spec)

    dataset_path = dataset_config_path or (ROOT / "configs" / "datasets.json")
    registry = DatasetRegistry(dataset_path)
    dataset_key = dataset_id or "shadow_eval"
    handle = registry.resolve(dataset_key)
    if handle is None:
        trace = ShadowTrace(status="VIOLATION", failing_test=None, counterexample=None)
        return ShadowResult("FAIL", "VIOLATION", None, None, None, None, runtime_hint, 0, 0, forager_count, trace)

    work_dir = ROOT
    script_path = (work_dir / script).resolve()
    try:
        script_path.relative_to(work_dir)
    except ValueError:
        trace = ShadowTrace(status="VIOLATION", failing_test=None, counterexample=None)
        return ShadowResult("FAIL", "VIOLATION", None, None, None, None, runtime_hint, 0, 0, forager_count, trace)
    if not script_path.exists():
        trace = ShadowTrace(status="ERROR", failing_test=None, counterexample=None)
        return ShadowResult("FAIL", "ERROR", None, None, None, None, runtime_hint, 0, 0, forager_count, trace)

    timeout_s = float(resource_spec.get("max_wall_time_ms", 1000)) / 1000.0

    env = {
        "PYTHONHASHSEED": str(seed),
        "PYTHONIOENCODING": "utf-8",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "GENESIS_DATASET_PATH": str(handle.path),
        "GENESIS_DATASET_ID": handle.dataset_id,
    }
    env.update({k: os.environ.get(k, "") for k in ("PATH", "PYTHONPATH", "TMPDIR")})

    result = _run_command(["python3", str(script_path), *map(str, args)], work_dir, timeout_s, env)
    if result.timed_out:
        trace = ShadowTrace(status="TIMEOUT", failing_test=None, counterexample=None)
        return ShadowResult("FAIL", "TIMEOUT", None, None, None, None, runtime_hint, 0, 0, forager_count, trace)

    if result.exit_code != 0:
        trace = ShadowTrace(status="ERROR", failing_test=None, counterexample=None)
        return ShadowResult("FAIL", "ERROR", None, None, None, None, runtime_hint, 0, 0, forager_count, trace)

    try:
        payload = _parse_output(result.stdout)
    except Exception:
        trace = ShadowTrace(status="VIOLATION", failing_test=None, counterexample=None)
        return ShadowResult("FAIL", "VIOLATION", None, None, None, None, runtime_hint, 0, 0, forager_count, trace)

    tests = payload.get("tests") or []
    for test in tests:
        if not test.get("passed", False):
            trace = ShadowTrace(status="TEST_FAIL", failing_test=test.get("name"), counterexample=test.get("input"))
            return ShadowResult("FAIL", "TEST_FAIL", None, None, None, None, runtime_hint, 0, len(tests), forager_count, trace)

    if forager_max_tests > 0:
        forager_tests = generate_tests(capsule, counterexamples, seed, forager_max_tests)
        forager_count = len(forager_tests)
        ok, failing = evaluate_tests(capsule, forager_tests)
        if not ok and failing is not None:
            trace = ShadowTrace(
                status="TEST_FAIL",
                failing_test=f"forager:{failing.test_id}",
                counterexample={"input": failing.input_value},
            )
            return ShadowResult("FAIL", "TEST_FAIL", None, None, None, None, runtime_hint, 0, len(tests), forager_count, trace)

    metrics = payload.get("metrics") or {}
    stat_spec = capsule.get("contract", {}).get("statistical_spec", {})
    metrics_spec = stat_spec.get("metrics", [])
    if not metrics_spec:
        trace = ShadowTrace(status="VIOLATION", failing_test=None, counterexample=None)
        return ShadowResult("FAIL", "VIOLATION", None, None, None, None, runtime_hint, 0, 0, forager_count, trace)

    metric_clause = metrics_spec[0]
    metric_name = metric_clause.get("name")
    metric_value = metrics.get(metric_name)
    if not isinstance(metric_value, (int, float)):
        trace = ShadowTrace(status="ERROR", failing_test=None, counterexample=None)
        return ShadowResult("FAIL", "ERROR", metric_name, None, None, None, runtime_hint, 0, 0, forager_count, trace)

    delta = (stat_spec.get("confidence_requirement") or {}).get("delta", 0.01)
    try:
        delta = float(delta)
    except Exception:
        delta = 0.01

    n = _determine_n(metrics, resource_spec)
    if n <= 0:
        trace = ShadowTrace(status="VIOLATION", failing_test=None, counterexample=None)
        return ShadowResult(
            "FAIL",
            "VIOLATION",
            metric_name,
            float(metric_value),
            None,
            None,
            runtime_hint,
            0,
            0,
            forager_count,
            trace,
        )

    direction = metric_clause.get("direction", "maximize")
    threshold = float(metric_clause.get("target", 0))

    tests_total = len(tests)
    tests_passed = sum(1 for test in tests if test.get("passed", False))

    if direction == "maximize":
        lcb = hoeffding_lcb(float(metric_value), n, delta)
        decision = "PASS" if lcb.bound >= threshold + margin else "FAIL"
        status = "OK" if decision == "PASS" else "TEST_FAIL"
        trace = (
            None
            if decision == "PASS"
            else ShadowTrace(
                "TEST_FAIL",
                "metric_threshold",
                {"bound": lcb.bound, "threshold": threshold, "margin": margin},
            )
        )
        return ShadowResult(
            decision,
            status,
            metric_name,
            float(metric_value),
            lcb.bound,
            threshold,
            runtime_hint,
            tests_passed,
            tests_total,
            forager_count,
            trace,
        )

    if direction == "minimize":
        ucb = hoeffding_ucb(float(metric_value), n, delta)
        decision = "PASS" if ucb.bound <= threshold - margin else "FAIL"
        status = "OK" if decision == "PASS" else "TEST_FAIL"
        trace = (
            None
            if decision == "PASS"
            else ShadowTrace(
                "TEST_FAIL",
                "metric_threshold",
                {"bound": ucb.bound, "threshold": threshold, "margin": margin},
            )
        )
        return ShadowResult(
            decision,
            status,
            metric_name,
            float(metric_value),
            ucb.bound,
            threshold,
            runtime_hint,
            tests_passed,
            tests_total,
            forager_count,
            trace,
        )

    trace = ShadowTrace(status="VIOLATION", failing_test=None, counterexample=None)
    return ShadowResult(
        "FAIL",
        "VIOLATION",
        metric_name,
        float(metric_value),
        None,
        threshold,
        runtime_hint,
        tests_passed,
        tests_total,
        forager_count,
        trace,
    )
