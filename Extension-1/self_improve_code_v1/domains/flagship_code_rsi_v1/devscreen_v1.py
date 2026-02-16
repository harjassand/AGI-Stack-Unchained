"""Devscreen execution for flagship domain (v1)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Dict, List, Tuple

from .fail_signature_v1 import failure_signature, normalize_log


def _stable_fail_kind(exit_code: int, timed_out: bool) -> str:
    if timed_out:
        return "TIMEOUT"
    if exit_code == 0:
        return "TEST_FAIL"
    return "RUNTIME_EXC"


def _truncate(text: str, limit: int = 2000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit]


def _run_stub(seed: int) -> Tuple[bool, str, str]:
    log = f"stub_devscreen seed={seed}"
    return False, "TEST_FAIL", log


def _run_code_agentic_ladder(workspace_dir: str, seed: int, timeout_s: int) -> Tuple[bool, str, str]:
    out_dir = os.path.join(workspace_dir, "_flagship_devscreen_out")
    os.makedirs(out_dir, exist_ok=True)
    script = (
        "from pathlib import Path; "
        "from system_runtime.tasks.code_agentic_v1.ceiling_ladder_code_agentic_v1 "
        "import run_ceiling_ladder; "
        f"run_ceiling_ladder(seed={int(seed)}, out_dir=Path('{out_dir}'), profile='dev')"
    )
    env = os.environ.copy()
    env.update(
        {
            "PYTHONHASHSEED": "0",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "LC_ALL": "C",
            "TZ": "UTC",
            "PYTHONPATH": workspace_dir + os.pathsep + env.get("PYTHONPATH", ""),
        }
    )
    try:
        proc = subprocess.run(
            [sys.executable, "-c", script],
            cwd=workspace_dir,
            env=env,
            capture_output=True,
            timeout=max(1, int(timeout_s)),
        )
        stdout = (proc.stdout or b"").decode("utf-8", errors="replace")
        stderr = (proc.stderr or b"").decode("utf-8", errors="replace")
        log = stdout + "\n" + stderr
        ok = proc.returncode == 0
        return ok, _stable_fail_kind(proc.returncode, False), log
    except subprocess.TimeoutExpired as exc:
        log = (exc.stdout or b"").decode("utf-8", errors="replace") + "\n" + (exc.stderr or b"").decode(
            "utf-8", errors="replace"
        )
        return False, "TIMEOUT", log


def run_devscreen(
    cfg: Dict,
    workspace_dir: str,
    seed: int,
    implicated_paths: List[str],
) -> Dict:
    if not cfg.get("enabled", True):
        normalized = ""
        return {
            "ok": True,
            "fail_signature": failure_signature(normalized),
            "fail_kind": "TEST_FAIL",
            "implicated_paths": implicated_paths,
            "distance": {"failing_tests": 0, "errors": 0},
            "normalized_log": normalized,
        }

    suite_id = str(cfg.get("suite_id", ""))
    timeout_s = int(cfg.get("timeout_s", 600))

    if suite_id == "stub":
        ok, fail_kind, log = _run_stub(seed)
    else:
        ok, fail_kind, log = _run_code_agentic_ladder(workspace_dir, seed, timeout_s)

    normalized = normalize_log(log)
    normalized = _truncate(normalized)
    failsig = failure_signature(normalized)
    return {
        "ok": bool(ok),
        "fail_signature": failsig,
        "fail_kind": "TEST_FAIL" if ok else fail_kind,
        "implicated_paths": implicated_paths,
        "distance": {"failing_tests": 0 if ok else 1, "errors": 0 if ok else 1},
        "normalized_log": normalized,
    }


__all__ = ["run_devscreen"]
