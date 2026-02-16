"""Fail-closed verifier for Omega self-optimize-core campaign."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .omega_common_v1 import OmegaV18Error, fail, load_canon_dict, repo_root


_GATE_STATUS_RE = re.compile(r"- Gate ([A-Z]).*\*\*(PASS|FAIL|SKIP)\*\*")


def _resolve_state(path: Path) -> Path:
    root = path.resolve()
    daemon_state = root / "daemon" / "rsi_omega_self_optimize_core_v1" / "state"
    if daemon_state.exists() and daemon_state.is_dir():
        return daemon_state
    if (root / "reports").is_dir() and (root / "promotion").is_dir():
        return root
    if root.name == "state" and root.parent.name == "rsi_omega_self_optimize_core_v1":
        return root
    fail("SCHEMA_FAIL")
    return root


def _run_cmd(cmd: list[str], *, cwd: Path) -> tuple[bool, str]:
    run = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    merged = "\n".join([run.stdout, run.stderr]).strip()
    tail = "\n".join(merged.splitlines()[-40:])
    return int(run.returncode) == 0, tail


def _extract_gate_statuses(summary_path: Path) -> dict[str, str]:
    if not summary_path.exists() or not summary_path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in summary_path.read_text(encoding="utf-8").splitlines():
        match = _GATE_STATUS_RE.search(line)
        if not match:
            continue
        out[str(match.group(1))] = str(match.group(2))
    return out


def _improvement_gate(report: dict[str, Any]) -> bool:
    before_after = report.get("before_after")
    if not isinstance(before_after, dict):
        fail("SCHEMA_FAIL")
    stps = before_after.get("stps_non_noop_q32")
    dispatch = before_after.get("dispatch_ns_median_u64")
    subverify = before_after.get("subverify_ns_median_u64")
    if not isinstance(stps, dict) or not isinstance(dispatch, dict) or not isinstance(subverify, dict):
        fail("SCHEMA_FAIL")

    stps_before = max(0, int(stps.get("before_q32", 0)))
    stps_after = max(0, int(stps.get("after_q32", 0)))
    if stps_before <= 0:
        stps_improved = stps_after > 0
    else:
        stps_improved = int(stps_after) * 100 >= int(stps_before) * 110

    dispatch_before = max(0, int(dispatch.get("before_u64", 0)))
    dispatch_after = max(0, int(dispatch.get("after_u64", 0)))
    subverify_before = max(0, int(subverify.get("before_u64", 0)))
    subverify_after = max(0, int(subverify.get("after_u64", 0)))
    dispatch_improved = dispatch_before > 0 and int(dispatch_after) * 100 <= int(dispatch_before) * 85
    subverify_improved = subverify_before > 0 and int(subverify_after) * 100 <= int(subverify_before) * 85
    return bool(stps_improved or dispatch_improved or subverify_improved)


def verify(state_dir: Path, *, mode: str) -> str:
    if mode != "full":
        fail("MODE_UNSUPPORTED")
    state_root = _resolve_state(state_dir)
    report_path = state_root / "reports" / "core_opt_report_v1.json"
    if not report_path.exists() or not report_path.is_file():
        fail("MISSING_STATE_INPUT")
    report = load_canon_dict(report_path)
    if str(report.get("schema_version", "")).strip() != "core_opt_report_v1":
        fail("SCHEMA_FAIL")

    root = repo_root()
    ok, output = _run_cmd([sys.executable, "-m", "pytest", "CDEL-v2/cdel/v18_0/tests_omega_daemon", "-q"], cwd=root)
    if not ok:
        fail("VERIFY_ERROR")

    ok, output = _run_cmd(
        [
            sys.executable,
            "-m",
            "pytest",
            "CDEL-v2/cdel/v18_0/tests_omega_daemon/test_tick_determinism.py",
            "-q",
        ],
        cwd=root,
    )
    if not ok:
        fail("VERIFY_ERROR")

    bench_root = state_root / "coreopt_eval_runs"
    shutil.rmtree(bench_root, ignore_errors=True)
    bench_root.mkdir(parents=True, exist_ok=True)
    bench_cmd = [
        sys.executable,
        str(root / "tools" / "omega" / "omega_benchmark_suite_v1.py"),
        "--ticks",
        "50",
        "--series_prefix",
        "coreopt_eval",
        "--runs_root",
        str(bench_root),
    ]
    ok, output = _run_cmd(bench_cmd, cwd=root)
    if not ok:
        fail("VERIFY_ERROR")

    bench_summary_path = bench_root / "coreopt_eval" / "OMEGA_BENCHMARK_SUMMARY_v1.md"
    gate_status = _extract_gate_statuses(bench_summary_path)
    if gate_status.get("A") != "PASS" or gate_status.get("B") != "PASS" or gate_status.get("D") != "PASS":
        fail("VERIFY_ERROR")

    if not _improvement_gate(report):
        fail("VERIFY_ERROR")
    return "VALID"


def main() -> None:
    parser = argparse.ArgumentParser(prog="verify_rsi_omega_self_optimize_core_v1")
    parser.add_argument("--mode", required=True)
    parser.add_argument("--state_dir", required=True)
    args = parser.parse_args()

    try:
        print(verify(Path(args.state_dir), mode=str(args.mode)))
    except OmegaV18Error as exc:
        msg = str(exc)
        if not msg.startswith("INVALID:"):
            msg = f"INVALID:{msg}"
        print(msg)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
