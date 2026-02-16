#!/usr/bin/env python3
"""Deterministic risk-based test router for Omega v18.0."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    _value = str(_entry)
    if _value not in sys.path:
        sys.path.insert(0, _value)

from cdel.v18_0.omega_common_v1 import canon_hash_obj, hash_file_stream, tree_hash

_HIGH_RISK_PATHS_EXACT = {
    "CDEL-v2/cdel/v18_0/verify_rsi_omega_daemon_v1.py",
    "CDEL-v2/cdel/v18_0/omega_allowlists_v1.py",
}
_HIGH_RISK_PREFIXES = ("meta-core/engine/", "orchestrator/omega_v18_0/")
_MEDIUM_RISK_PREFIXES = ("CDEL-v2/cdel/v18_0/", "tools/omega/")
_LOW_RISK_PREFIXES = ("tools/polymath/", "domains/", "polymath/")
_TEST_ENV_STRIP_KEYS = (
    "OMEGA_POLYMATH_STORE_ROOT",
    "OMEGA_TICK_U64",
    "OMEGA_RUN_SEED_U64",
)


def _load_touched_paths(value: str) -> list[str]:
    raw = str(value).strip()
    if not raw:
        raise RuntimeError("SCHEMA_FAIL")
    payload: Any
    if raw.startswith("["):
        payload = json.loads(raw)
    else:
        payload = json.loads(Path(raw).resolve().read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError("SCHEMA_FAIL")
    rows: list[str] = []
    for row in payload:
        value = str(row).strip().replace("\\", "/")
        if not value:
            continue
        if value.startswith("./"):
            value = value[2:]
        if value.startswith("/"):
            raise RuntimeError("SCHEMA_FAIL")
        rows.append(value)
    return sorted(set(rows))


def classify_risk(touched_paths: list[str]) -> str:
    if any(path in _HIGH_RISK_PATHS_EXACT for path in touched_paths):
        return "HIGH"
    if any(any(path.startswith(prefix) for prefix in _HIGH_RISK_PREFIXES) for path in touched_paths):
        return "HIGH"
    if touched_paths and all(any(path.startswith(prefix) for prefix in _LOW_RISK_PREFIXES) for path in touched_paths):
        return "LOW"
    if any(any(path.startswith(prefix) for prefix in _MEDIUM_RISK_PREFIXES) for path in touched_paths):
        return "MEDIUM"
    return "MEDIUM"


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _inject_xdist_if_available(cmd: list[str]) -> list[str]:
    if len(cmd) < 3:
        return list(cmd)
    if cmd[1:3] != ["-m", "pytest"]:
        return list(cmd)
    if any(value == "-n" for value in cmd):
        return list(cmd)
    if importlib.util.find_spec("xdist") is None:
        return list(cmd)
    return [cmd[0], "-m", "pytest", "-n", "auto", *cmd[3:]]


def _run_cmd(*, cmd: list[str], cwd: Path) -> dict[str, Any]:
    cmd = _inject_xdist_if_available(cmd)
    started = time.monotonic()
    child_env = {**os.environ}
    for key in _TEST_ENV_STRIP_KEYS:
        child_env.pop(key, None)
    child_env["PYTHONPATH"] = f"{cwd}:{cwd / 'CDEL-v2'}:{child_env.get('PYTHONPATH', '')}".rstrip(":")
    run = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env=child_env,
    )
    duration_ms = int((time.monotonic() - started) * 1000)
    return {
        "name": " ".join(shlex.quote(row) for row in cmd),
        "cmd": cmd,
        "duration_ms": duration_ms,
        "return_code": int(run.returncode),
        "pass_b": int(run.returncode) == 0,
        "stdout_hash": _sha256_text(run.stdout),
        "stderr_hash": _sha256_text(run.stderr),
    }


def _resolve_globs(patterns: list[str], *, repo_root: Path) -> list[Path]:
    out: set[Path] = set()
    for pattern in patterns:
        path = repo_root / pattern
        if path.is_file():
            out.add(path.resolve())
            continue
        rows = sorted(repo_root.glob(pattern), key=lambda row: row.as_posix())
        for row in rows:
            if row.is_file():
                out.add(row.resolve())
    return sorted(out)


def _source_roots_for_risk(risk_level: str) -> list[str]:
    if risk_level == "HIGH":
        return ["CDEL-v2/cdel/v18_0", "orchestrator/omega_v18_0", "meta-core/engine"]
    if risk_level == "MEDIUM":
        return ["CDEL-v2/cdel/v18_0", "tools/omega"]
    return ["tools/polymath", "domains", "polymath"]


def _plan_for(*, mode: str, risk_level: str) -> dict[str, Any]:
    if mode == "promotion" and risk_level == "HIGH":
        return {
            "plan_id": "omega_promotion_high_v1",
            "tests": [
                {
                    "name": "omega_daemon_full_suite_parallel",
                    "cmd": [
                        sys.executable,
                        "tools/omega/run_v18_0_daemon_tests_parallel_v1.py",
                        "--pattern",
                        "CDEL-v2/cdel/v18_0/tests_omega_daemon/test_*.py",
                    ],
                }
            ],
            "test_file_globs": ["CDEL-v2/cdel/v18_0/tests_omega_daemon/test_*.py"],
        }
    if mode == "promotion" and risk_level == "MEDIUM":
        return {
            "plan_id": "omega_promotion_medium_v1",
            "tests": [
                {
                    "name": "omega_tick_determinism",
                    "cmd": [sys.executable, "-m", "pytest", "-q", "CDEL-v2/cdel/v18_0/tests_omega_daemon/test_tick_determinism.py"],
                },
                {
                    "name": "omega_verifier_recompute_decision",
                    "cmd": [
                        sys.executable,
                        "-m",
                        "pytest",
                        "-q",
                        "CDEL-v2/cdel/v18_0/tests_omega_daemon/test_verifier_recomputes_decision.py",
                    ],
                },
                {
                    "name": "omega_benchmark_smoke_ticks10",
                    "cmd": [
                        sys.executable,
                        "tools/omega/omega_benchmark_suite_v1.py",
                        "--ticks",
                        "10",
                        "--series_prefix",
                        "omega_router_smoke",
                        "--runs_root",
                        "runs/_omega_test_router",
                    ],
                },
            ],
            "test_file_globs": [
                "CDEL-v2/cdel/v18_0/tests_omega_daemon/test_tick_determinism.py",
                "CDEL-v2/cdel/v18_0/tests_omega_daemon/test_verifier_recomputes_decision.py",
            ],
        }
    if mode == "promotion" and risk_level == "LOW":
        return {
            "plan_id": "omega_promotion_low_v1",
            "tests": [
                {
                    "name": "polymath_phase17_fast_suite",
                    "cmd": [sys.executable, "-m", "pytest", "-q", "CDEL-v2/cdel/v18_0/tests_fast/test_polymath_phase17_fast.py"],
                },
                {
                    "name": "polymath_phase16_suite",
                    "cmd": [sys.executable, "-m", "pytest", "-q", "CDEL-v2/cdel/v18_0/tests_omega_daemon/test_polymath_phase16.py"],
                },
                {
                    "name": "polymath_phase17_suite",
                    "cmd": [sys.executable, "-m", "pytest", "-q", "CDEL-v2/cdel/v18_0/tests_omega_daemon/test_polymath_phase17.py"],
                },
            ],
            "test_file_globs": [
                "CDEL-v2/cdel/v18_0/tests_fast/test_polymath_phase17_fast.py",
                "CDEL-v2/cdel/v18_0/tests_omega_daemon/test_polymath_phase16.py",
                "CDEL-v2/cdel/v18_0/tests_omega_daemon/test_polymath_phase17.py",
            ],
        }
    if mode == "triage" and risk_level == "HIGH":
        return {
            "plan_id": "omega_triage_high_v1",
            "tests": [
                {
                    "name": "omega_tick_determinism",
                    "cmd": [sys.executable, "-m", "pytest", "-q", "CDEL-v2/cdel/v18_0/tests_omega_daemon/test_tick_determinism.py"],
                },
                {
                    "name": "omega_decision_recompute",
                    "cmd": [sys.executable, "-m", "pytest", "-q", "CDEL-v2/cdel/v18_0/tests_omega_daemon/test_decision_recomputable.py"],
                },
            ],
            "test_file_globs": [
                "CDEL-v2/cdel/v18_0/tests_omega_daemon/test_tick_determinism.py",
                "CDEL-v2/cdel/v18_0/tests_omega_daemon/test_decision_recomputable.py",
            ],
        }
    if mode == "triage" and risk_level == "MEDIUM":
        return {
            "plan_id": "omega_triage_medium_v1",
            "tests": [
                {
                    "name": "omega_goal_synth_deterministic",
                    "cmd": [
                        sys.executable,
                        "-m",
                        "pytest",
                        "-q",
                        "CDEL-v2/cdel/v18_0/tests_omega_daemon/test_goal_synthesizer_deterministic.py",
                    ],
                },
                {
                    "name": "omega_tick_determinism",
                    "cmd": [sys.executable, "-m", "pytest", "-q", "CDEL-v2/cdel/v18_0/tests_omega_daemon/test_tick_determinism.py"],
                },
            ],
            "test_file_globs": [
                "CDEL-v2/cdel/v18_0/tests_omega_daemon/test_goal_synthesizer_deterministic.py",
                "CDEL-v2/cdel/v18_0/tests_omega_daemon/test_tick_determinism.py",
            ],
        }
    return {
        "plan_id": "omega_triage_low_v1",
        "tests": [
            {
                "name": "polymath_phase17_fast_suite",
                "cmd": [sys.executable, "-m", "pytest", "-q", "CDEL-v2/cdel/v18_0/tests_fast/test_polymath_phase17_fast.py"],
            }
        ],
        "test_file_globs": ["CDEL-v2/cdel/v18_0/tests_fast/test_polymath_phase17_fast.py"],
    }


def route_and_run(*, touched_paths: list[str], mode: str, repo_root: Path | None = None) -> dict[str, Any]:
    if mode not in {"triage", "promotion"}:
        raise RuntimeError("SCHEMA_FAIL")
    root = (repo_root or _REPO_ROOT).resolve()
    risk_level = classify_risk(touched_paths)
    plan = _plan_for(mode=mode, risk_level=risk_level)
    tests = plan["tests"]
    if not isinstance(tests, list):
        raise RuntimeError("SCHEMA_FAIL")

    results: list[dict[str, Any]] = []
    for row in tests:
        if not isinstance(row, dict):
            raise RuntimeError("SCHEMA_FAIL")
        cmd = row.get("cmd")
        if not isinstance(cmd, list) or not cmd:
            raise RuntimeError("SCHEMA_FAIL")
        results.append(_run_cmd(cmd=[str(value) for value in cmd], cwd=root))

    test_files = _resolve_globs([str(value) for value in plan.get("test_file_globs", [])], repo_root=root)
    test_file_hashes = [{"path": path.relative_to(root).as_posix(), "sha256": hash_file_stream(path)} for path in test_files]

    source_hash_rows: list[dict[str, str]] = []
    for rel in _source_roots_for_risk(risk_level):
        abs_path = (root / rel).resolve()
        if not abs_path.exists():
            continue
        if abs_path.is_file():
            digest = hash_file_stream(abs_path)
        else:
            digest = tree_hash(abs_path)
        source_hash_rows.append({"path": rel, "sha256": digest})
    source_hash_rows = sorted(source_hash_rows, key=lambda row: row["path"])
    repo_tree_hash = canon_hash_obj({"sources": source_hash_rows})

    report: dict[str, Any] = {
        "schema_version": "OMEGA_TEST_ROUTER_REPORT_v1",
        "report_id": "sha256:" + ("0" * 64),
        "mode": mode,
        "risk_level": risk_level,
        "plan_id": str(plan.get("plan_id", "")),
        "touched_paths": sorted(set(str(row) for row in touched_paths)),
        "tests_run": results,
        "durations_ms": [int(row["duration_ms"]) for row in results],
        "result": "PASS" if all(bool(row.get("pass_b", False)) for row in results) else "FAIL",
        "test_file_hashes": test_file_hashes,
        "source_tree_hashes": source_hash_rows,
        "repo_tree_hash": repo_tree_hash,
        "xdist_available_b": bool(importlib.util.find_spec("xdist") is not None),
    }
    no_id = dict(report)
    no_id.pop("report_id", None)
    report["report_id"] = canon_hash_obj(no_id)
    return report


def build_test_plan_receipt(*, report: dict[str, Any], touched_paths: list[str]) -> dict[str, Any]:
    plan_id = str(report.get("plan_id", "")).strip()
    risk_level = str(report.get("risk_level", "")).strip()
    result = str(report.get("result", "FAIL")).strip()
    if not plan_id or risk_level not in {"LOW", "MEDIUM", "HIGH"} or result not in {"PASS", "FAIL"}:
        raise RuntimeError("SCHEMA_FAIL")
    tests = report.get("tests_run")
    if not isinstance(tests, list):
        raise RuntimeError("SCHEMA_FAIL")
    tests_run = [str(row.get("name", "")).strip() for row in tests if isinstance(row, dict)]
    durations_ms = [max(0, int(row.get("duration_ms", 0))) for row in tests if isinstance(row, dict)]
    if len(tests_run) != len(durations_ms):
        raise RuntimeError("SCHEMA_FAIL")
    test_files = sorted(
        {
            str(row.get("path", "")).strip()
            for row in (report.get("test_file_hashes") or [])
            if isinstance(row, dict) and str(row.get("path", "")).strip()
        }
    )
    repo_tree_hash = str(report.get("repo_tree_hash", "")).strip()
    inputs_hash = canon_hash_obj(
        {
            "touched_paths": sorted(set(str(row) for row in touched_paths)),
            "plan_id": plan_id,
            "test_files": test_files,
            "repo_tree_hash": repo_tree_hash,
        }
    )
    return {
        "schema_version": "omega_test_plan_receipt_v1",
        "receipt_id": "sha256:" + ("0" * 64),
        "plan_id": plan_id,
        "risk_level": risk_level,
        "tests_run": tests_run,
        "durations_ms": durations_ms,
        "test_files": test_files,
        "repo_tree_hash": repo_tree_hash,
        "touched_paths": sorted(set(str(row) for row in touched_paths)),
        "result": result,
        "inputs_hash": inputs_hash,
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="omega_test_router_v1")
    parser.add_argument("--touched_paths_json", required=True)
    parser.add_argument("--mode", required=True, choices=["triage", "promotion"])
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    touched_paths = _load_touched_paths(args.touched_paths_json)
    report = route_and_run(touched_paths=touched_paths, mode=str(args.mode), repo_root=_REPO_ROOT)
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(out_path.as_posix())


if __name__ == "__main__":
    main()
