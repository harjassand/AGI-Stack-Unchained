"""Candidate ID computation (v1)."""

from __future__ import annotations

import importlib
import os
import sys
from typing import Dict, Tuple, Optional, Any

from ..canon.json_canon_v1 import canon_bytes
from ..canon.hash_v1 import sha256_bytes, sha256_hex

DS = b"repo_patch_candidate_v1\x00"

_BACKEND_CFG: Optional[Dict[str, Any]] = None
_BACKEND_FN = None


def set_candidate_id_backend(cfg: Dict[str, Any], base_dir: Optional[str] = None) -> None:
    global _BACKEND_CFG, _BACKEND_FN
    if not isinstance(cfg, dict):
        raise ValueError("candidate_id backend config must be dict")
    backend = cfg.get("backend")
    if not backend:
        raise ValueError("candidate_id backend missing")
    pythonpath_add = cfg.get("pythonpath_add", [])
    if base_dir is None:
        base_dir = os.getcwd()
    abs_paths = []
    for p in pythonpath_add:
        if not isinstance(p, str):
            raise ValueError("candidate_id pythonpath_add entries must be strings")
        if os.path.isabs(p):
            abs_paths.append(p)
        else:
            abs_paths.append(os.path.abspath(os.path.join(base_dir, p)))
    _BACKEND_CFG = dict(cfg)
    _BACKEND_CFG["pythonpath_add"] = abs_paths
    _BACKEND_FN = None


def _ensure_backend() -> Dict[str, Any]:
    if _BACKEND_CFG is None:
        raise RuntimeError("candidate_id backend not configured")
    return _BACKEND_CFG


def _load_re2_function(cfg: Dict[str, Any]):
    global _BACKEND_FN
    if _BACKEND_FN is not None:
        return _BACKEND_FN
    for p in cfg.get("pythonpath_add", []):
        if p and p not in sys.path:
            sys.path.insert(0, p)
    import_path = cfg.get("import_path")
    func_name = cfg.get("function")
    if not import_path or not func_name:
        raise RuntimeError("candidate_id backend missing import_path/function")
    try:
        mod = importlib.import_module(import_path)
        fn = getattr(mod, func_name)
    except Exception as e:
        raise RuntimeError(f"candidate_id backend import failed: {e}")
    _BACKEND_FN = fn
    return fn


def _coerce_candidate_id(result: Any) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, (list, tuple)) and result:
        return str(result[0])
    if isinstance(result, dict) and "candidate_id" in result:
        return str(result["candidate_id"])
    raise RuntimeError("candidate_id backend returned unsupported result")


def _stub_candidate_id(manifest: Dict, patch_bytes: bytes) -> str:
    manifest_for_hash = dict(manifest)
    manifest_for_hash.pop("candidate_id", None)
    data = b"stub_candidate_id_v1\x00" + canon_bytes(manifest_for_hash) + patch_bytes
    return sha256_hex(data)


def compute_candidate_id(manifest: Dict, patch_bytes: bytes) -> Tuple[str, str, str, str]:
    cfg = _ensure_backend()
    backend = cfg.get("backend")
    if backend == "re2_authoritative_fail_closed_v1":
        fn = _load_re2_function(cfg)
        result = fn(manifest, patch_bytes)
        cand_id = _coerce_candidate_id(result)
        return cand_id, "", "", ""
    if backend == "stub_deterministic_v1":
        cand_id = _stub_candidate_id(manifest, patch_bytes)
        return cand_id, "", "", ""
    raise RuntimeError(f"unsupported candidate_id backend: {backend}")


def patch_sha256_hex(patch_bytes: bytes) -> str:
    return sha256_hex(patch_bytes)


__all__ = ["compute_candidate_id", "patch_sha256_hex", "DS", "set_candidate_id_backend"]
