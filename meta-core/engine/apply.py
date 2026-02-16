import fcntl
import os
from typing import Any, Dict, Tuple

from activation import canary_staged, commit_staged, stage_bundle, verify_staged
from constants import ACTIVE_DIRNAME
from errors import InternalError


def apply_bundle(meta_core_root: str, bundle_dir: str) -> Tuple[int, Dict[str, Any]]:
    active_dir = os.path.join(meta_core_root, ACTIVE_DIRNAME)
    lock_path = os.path.join(active_dir, "LOCK")
    os.makedirs(active_dir, exist_ok=True)

    lock_fd = open(lock_path, "a+")
    fcntl.flock(lock_fd, fcntl.LOCK_EX)

    try:
        work_dir = os.path.join(active_dir, "work")
        stage_code, stage_out = stage_bundle(meta_core_root, bundle_dir, work_dir)
        if stage_code != 0:
            verdict = "REJECTED" if stage_code == 2 else "INTERNAL_ERROR"
            return stage_code, {"verdict": verdict}

        stage_path = stage_out.get("stage_path")
        if not isinstance(stage_path, str):
            return 1, {"verdict": "INTERNAL_ERROR"}

        receipt_path = os.path.join(work_dir, "receipt.json")
        verify_code, _ = verify_staged(meta_core_root, stage_path, receipt_path)
        if verify_code != 0:
            verdict = "REJECTED" if verify_code == 2 else "INTERNAL_ERROR"
            return verify_code, {"verdict": verdict}

        canary_code, _ = canary_staged(meta_core_root, stage_path, work_dir)
        if canary_code != 0:
            verdict = "REJECTED" if canary_code == 2 else "INTERNAL_ERROR"
            return canary_code, {"verdict": verdict}

        commit_code, commit_out = commit_staged(meta_core_root, stage_path, receipt_path)
        if commit_code == 0:
            return 0, {"verdict": "APPLIED", "active_bundle_hash": commit_out.get("active_bundle_hash")}
        verdict = "INTERNAL_ERROR" if commit_code == 1 else "REJECTED"
        return commit_code, {"verdict": verdict}
    except InternalError:
        return 1, {"verdict": "INTERNAL_ERROR"}
    except Exception:  # noqa: BLE001
        return 1, {"verdict": "INTERNAL_ERROR"}
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            lock_fd.close()
