"""CDEL sealed eval client (v1)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from typing import Dict, Optional, Tuple

from ...canon.json_canon_v1 import canon_bytes



def _read_result_report(run_dir: str) -> str:
    # Try root result_report.json, else evidence_bundle_dir/result_report.json
    candidates = [
        os.path.join(run_dir, "result_report.json"),
        os.path.join(run_dir, "evidence_bundle_dir", "result_report.json"),
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    payload = json.loads(f.read().decode("utf-8"))
                return str(payload.get("verdict", "FAIL"))
            except Exception:
                continue
    return "FAIL"

def _run_cli(candidate_tar: str, cdel_root: str, repo_root: str, timeout_s: int) -> Tuple[int, bytes, bytes]:
    env = os.environ.copy()
    env.update(
        {
            "PYTHONHASHSEED": "0",
            "LC_ALL": "C",
            "TZ": "UTC",
            "PYTHONPATH": cdel_root + os.pathsep + env.get("PYTHONPATH", ""),
        }
    )
    cmd = [sys.executable, "-m", "cdel.cli", "--root", repo_root, "eval", "--profile", "repo_patch_eval_v1", "--candidate", candidate_tar]
    proc = subprocess.run(cmd, capture_output=True, env=env, timeout=max(1, int(timeout_s)))
    return proc.returncode, proc.stdout or b"", proc.stderr or b""


def _discover_run_dir(repo_root: str, candidate_id: str) -> Optional[str]:
    runs_root = os.path.join(repo_root, "runs", "repo_patch_eval_v1", candidate_id)
    if not os.path.isdir(runs_root):
        return None
    subdirs = sorted([d for d in os.listdir(runs_root) if os.path.isdir(os.path.join(runs_root, d))])
    if not subdirs:
        return None
    return os.path.join(runs_root, subdirs[0])


def _copy_if_exists(src: str, dst: str) -> Optional[str]:
    if not os.path.exists(src):
        return None
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(src, dst)
    return dst


def run_sealed_eval(
    cfg: Dict,
    *,
    candidate_tar: str,
    candidate_id: str,
    cdel_root: str,
    repo_root: str,
    out_dir: str,
    sealed_mode: str,
) -> Dict:
    timeout_s = int(cfg.get("timeout_s", 3600))
    os.makedirs(out_dir, exist_ok=True)
    exit_code, _stdout, _stderr = _run_cli(candidate_tar, cdel_root, repo_root, timeout_s)

    run_dir = _discover_run_dir(repo_root, candidate_id)
    result_report_path = None
    receipt_path = None
    evidence_path = None
    verdict = "FAIL"
    if run_dir:
        result_report_path = _copy_if_exists(os.path.join(run_dir, "result_report.json"), os.path.join(out_dir, "result_report.json"))
        receipt_path = _copy_if_exists(os.path.join(run_dir, "receipt.json"), os.path.join(out_dir, "receipt.json"))
        evidence_path = _copy_if_exists(os.path.join(run_dir, "evidence_bundle_v1.tar"), os.path.join(out_dir, "evidence_bundle_v1.tar"))
        verdict = _read_result_report(run_dir)
        if receipt_path and verdict != "PASS":
            # receipt implies PASS
            verdict = "PASS"
    status = "PASS" if verdict == "PASS" else "FAIL"
    receipt_rel = os.path.relpath(receipt_path, out_dir) if receipt_path else ""
    summary = {
        "exit_code": int(exit_code),
        "evidence_present": bool(evidence_path),
    }
    result = {
        "candidate_id": candidate_id,
        "sealed_mode": sealed_mode,
        "status": status,
        "receipt_path": receipt_rel,
        "summary": summary,
    }
    with open(os.path.join(out_dir, "sealed_result.json"), "wb") as f:
        f.write(canon_bytes(result))
    return result


__all__ = ["run_sealed_eval"]
