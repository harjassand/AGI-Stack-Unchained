"""Devscreen execution (v1)."""

from __future__ import annotations

import json
import os
import subprocess
import py_compile
from typing import Dict, List

from ..canon.hash_v1 import sha256_hex


def _json_pointer(doc, pointer: str):
    if pointer == "" or pointer == "/":
        return doc
    if not pointer.startswith("/"):
        raise ValueError("json pointer must start with /")
    parts = pointer.split("/")[1:]
    cur = doc
    for part in parts:
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(cur, list):
            idx = int(part)
            cur = cur[idx]
        elif isinstance(cur, dict):
            cur = cur[part]
        else:
            raise ValueError("json pointer traversal failed")
    return cur


def _fastcheck_py_compile(paths: List[str]) -> bool:
    for path in paths:
        if not path.endswith(".py"):
            continue
        try:
            py_compile.compile(path, doraise=True)
        except py_compile.PyCompileError:
            return False
    return True


def _fastcheck_denylist(paths: List[str], denylist: List[str]) -> bool:
    if not denylist:
        return True
    for path in paths:
        try:
            with open(path, "rb") as f:
                data = f.read().decode("utf-8", errors="ignore")
        except OSError:
            return False
        for token in denylist:
            if token in data:
                return False
    return True


def _digest_file(path: str) -> str:
    if not path or not os.path.exists(path):
        return sha256_hex(b"")
    with open(path, "rb") as f:
        return sha256_hex(f.read())


def _resolve_metric_path(workspace_dir: str, metric_relpath: str, alt_dirs: List[str]) -> str:
    if not metric_relpath:
        return ""
    primary = os.path.join(workspace_dir, metric_relpath)
    if os.path.exists(primary):
        return primary
    for d in alt_dirs:
        cand = os.path.join(d, metric_relpath)
        if os.path.exists(cand):
            return cand
    return primary


def run_devscreen(
    cfg: Dict,
    workspace_dir: str,
    edited_files: List[str],
    baseline_m_bp: int,
    patch_path: str,
    candidate_path: str,
) -> Dict:
    denylist = cfg.get("denylist_tokens", [])
    fastcheck_ok = True
    if cfg.get("fastcheck_py_compile", True):
        fastcheck_ok = _fastcheck_py_compile(edited_files)
    if fastcheck_ok:
        fastcheck_ok = _fastcheck_denylist(edited_files, denylist)
    if not fastcheck_ok:
        return {
            "status": "FASTCHECK_FAIL",
            "m_bp": 0,
            "baseline_m_bp": int(baseline_m_bp),
            "costs": {"patch_bytes": os.path.getsize(patch_path) if os.path.exists(patch_path) else 0},
            "digests": {
                "metric_file": sha256_hex(b""),
                "patch.diff": _digest_file(patch_path),
                "candidate.tar": _digest_file(candidate_path),
            },
        }

    argv = cfg.get("argv", []) or cfg.get("devscreen_argv", [])
    cwd_rel = cfg.get("cwd", cfg.get("devscreen_cwd_rel", "."))
    env_cfg = cfg.get("env", cfg.get("devscreen_env", {}))
    env = os.environ.copy()
    env.update({str(k): str(v) for k, v in env_cfg.items()})
    timeout = cfg.get("timeout_sec", None)

    cwd = cwd_rel
    if not os.path.isabs(cwd_rel):
        cwd = os.path.join(workspace_dir, cwd_rel)

    try:
        subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "TIMEOUT",
            "m_bp": 0,
            "baseline_m_bp": int(baseline_m_bp),
            "costs": {"patch_bytes": os.path.getsize(patch_path) if os.path.exists(patch_path) else 0},
            "digests": {
                "metric_file": sha256_hex(b""),
                "patch.diff": _digest_file(patch_path),
                "candidate.tar": _digest_file(candidate_path),
            },
        }
    except Exception:
        return {
            "status": "CRASH",
            "m_bp": 0,
            "baseline_m_bp": int(baseline_m_bp),
            "costs": {"patch_bytes": os.path.getsize(patch_path) if os.path.exists(patch_path) else 0},
            "digests": {
                "metric_file": sha256_hex(b""),
                "patch.diff": _digest_file(patch_path),
                "candidate.tar": _digest_file(candidate_path),
            },
        }

    metric_cfg = cfg.get("metric", {}) if isinstance(cfg.get("metric", {}), dict) else {}
    metric_relpath = metric_cfg.get("file_relpath") or cfg.get("metric_file_relpath", "")
    metric_pointer = metric_cfg.get("json_pointer") or cfg.get("metric_json_pointer", "")
    alt_dirs = cfg.get("metric_alt_dirs", [])
    metric_path = _resolve_metric_path(workspace_dir, metric_relpath, alt_dirs)
    metric_digest = _digest_file(metric_path)
    try:
        with open(metric_path, "rb") as f:
            metric_doc = json.loads(f.read().decode("utf-8"))
        m_val = _json_pointer(metric_doc, metric_pointer)
        if isinstance(m_val, bool) or not isinstance(m_val, int):
            raise ValueError("metric not int")
        m_bp = int(m_val)
        status = "OK"
    except Exception:
        m_bp = 0
        status = "CRASH"

    return {
        "status": status,
        "m_bp": m_bp,
        "baseline_m_bp": int(baseline_m_bp),
        "costs": {"patch_bytes": os.path.getsize(patch_path) if os.path.exists(patch_path) else 0},
        "digests": {
            "metric_file": metric_digest,
            "patch.diff": _digest_file(patch_path),
            "candidate.tar": _digest_file(candidate_path),
        },
    }


__all__ = ["run_devscreen"]
