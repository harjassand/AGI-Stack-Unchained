"""CDEL submission and evidence discovery (v1)."""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Dict, Tuple, List

from ..canon.hash_v1 import sha256_hex
from ..canon.json_canon_v1 import canon_bytes


def _digest_bytes(data: bytes) -> str:
    return sha256_hex(data)


def _digest_file(path: str) -> str:
    if not os.path.exists(path):
        return sha256_hex(b"")
    with open(path, "rb") as f:
        return sha256_hex(f.read())


def _format_argv(argv: List[str], mapping: Dict[str, str]) -> List[str]:
    out: List[str] = []
    for arg in argv:
        new = arg
        for k, v in mapping.items():
            new = new.replace("{" + k + "}", v)
        out.append(new)
    return out


def run_cdel(cfg: Dict, candidate_tar: str, run_config_dir: str, out_dir: str) -> Tuple[Dict, str]:
    argv_template = cfg.get("argv", []) or cfg.get("cdel_argv", [])
    cwd_cfg = cfg.get("cwd", cfg.get("cdel_cwd_rel", "."))
    env_cfg = cfg.get("env", cfg.get("cdel_env", {}))

    if not os.path.isabs(cwd_cfg):
        cwd = os.path.abspath(os.path.join(run_config_dir, cwd_cfg))
    else:
        cwd = cwd_cfg

    os.makedirs(out_dir, exist_ok=True)
    mapping = {"candidate_tar": candidate_tar, "out_dir": out_dir}
    argv = _format_argv(argv_template, mapping)
    if not any("{candidate_tar}" in a for a in argv_template):
        if candidate_tar not in argv:
            argv = argv + [candidate_tar]

    env = os.environ.copy()
    env.update({str(k): str(v) for k, v in env_cfg.items()})
    proc = subprocess.run(argv, cwd=cwd, env=env, capture_output=True)
    stdout = proc.stdout or b""
    stderr = proc.stderr or b""
    invoke = {
        "exit_code": proc.returncode,
        "stdout_sha256": _digest_bytes(stdout),
        "stderr_sha256": _digest_bytes(stderr),
        "argv_sha256": _digest_bytes(canon_bytes(argv)),
        "env_sha256": _digest_bytes(canon_bytes(env_cfg)),
    }
    return invoke, out_dir


def discover_evidence(repo_root: str, candidate_id: str, selected_dir: str) -> Dict:
    runs_root = os.path.join(repo_root, "CDEL-v2", "runs", "repo_patch_eval_v1", candidate_id)
    if not os.path.isdir(runs_root):
        return {"cdel_discovery_status": "NOT_FOUND"}
    subdirs = sorted([d for d in os.listdir(runs_root) if os.path.isdir(os.path.join(runs_root, d))])
    if not subdirs:
        return {"cdel_discovery_status": "NOT_FOUND"}
    chosen = os.path.join(runs_root, subdirs[0])
    copied = {}
    mappings = {
        "result_report.json": "cdel_result_report.json",
        "receipt.json": "receipt.json",
        "evidence_bundle_v1.tar": "evidence_bundle_v1.tar",
    }
    for src_name, dst_name in mappings.items():
        src = os.path.join(chosen, src_name)
        if os.path.exists(src):
            dst = os.path.join(selected_dir, dst_name)
            shutil.copyfile(src, dst)
            copied[dst_name] = _digest_file(dst)
    if not copied:
        return {"cdel_discovery_status": "NOT_FOUND"}
    out = {"cdel_discovery_status": "COPIED"}
    out.update({"copied": copied})
    return out


def copy_stub_outputs(out_dir: str, selected_dir: str) -> Dict:
    copied = {}
    mappings = {
        "result_report.json": "cdel_result_report.json",
        "receipt.json": "receipt.json",
        "evidence_bundle_v1.tar": "evidence_bundle_v1.tar",
    }
    for src_name, dst_name in mappings.items():
        src = os.path.join(out_dir, src_name)
        if os.path.exists(src):
            dst = os.path.join(selected_dir, dst_name)
            shutil.copyfile(src, dst)
            copied[dst_name] = _digest_file(dst)
    if not copied:
        return {"cdel_discovery_status": "NOT_FOUND"}
    out = {"cdel_discovery_status": "COPIED"}
    out.update({"copied": copied})
    return out


__all__ = ["run_cdel", "discover_evidence", "copy_stub_outputs"]
