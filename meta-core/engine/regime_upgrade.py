import hashlib
import json
import os
from typing import Any, Dict, Tuple

from activation import commit_staged
from atomic_fs import atomic_write_text
from constants import (
    ACTIVE_DIRNAME,
    ACTIVE_NEXT_BUNDLE_FILENAME,
    FAILPOINT_AFTER_NEXT_WRITE,
    FAILPOINT_ENV,
    LEDGER_DIRNAME,
    LEDGER_LOG_FILENAME,
)
from errors import InternalError
from ledger import append_entry_crash_safe, make_regime_upgrade_entry, read_last_entry


def _is_hex_hash(value: str) -> bool:
    if len(value) != 64:
        return False
    for ch in value:
        if ch not in "0123456789abcdef":
            return False
    return True


def _read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_readiness_receipt(path: str) -> tuple[dict[str, Any], bytes]:
    with open(path, "rb") as f:
        raw = f.read()
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("INVALID")
    if payload.get("schema_name") != "shadow_regime_readiness_receipt_v1":
        raise RuntimeError("INVALID")
    if payload.get("schema_version") != "v19_0":
        raise RuntimeError("INVALID")
    return payload, raw


def commit_staged_regime_upgrade(
    meta_core_root: str,
    stage_path: str,
    receipt_path: str,
    readiness_receipt_path: str,
    *,
    auto_swap_b: bool = False,
) -> Tuple[int, Dict[str, Any]]:
    if (
        not os.path.isabs(meta_core_root)
        or not os.path.isabs(stage_path)
        or not os.path.isabs(receipt_path)
        or not os.path.isabs(readiness_receipt_path)
    ):
        return 1, {"verdict": "INTERNAL_ERROR"}

    try:
        readiness, readiness_raw = _load_readiness_receipt(readiness_receipt_path)
    except Exception:  # noqa: BLE001
        return 2, {"verdict": "INVALID", "reason_code": "SHADOW_READINESS_INVALID"}

    tier_a_pass = bool(readiness.get("tier_a_pass_b", False))
    tier_b_pass = bool(readiness.get("tier_b_pass_b", False))
    runtime_tier_b_pass = bool(readiness.get("runtime_tier_b_pass_b", False))
    if auto_swap_b and not runtime_tier_b_pass:
        return 2, {"verdict": "INVALID", "reason_code": "TIER_B_REQUIRED_FOR_SWAP"}
    if not (tier_a_pass and tier_b_pass and runtime_tier_b_pass):
        return 2, {"verdict": "INVALID", "reason_code": "SHADOW_READINESS_NOT_READY"}

    try:
        stage_desc = _read_json(stage_path)
    except Exception:  # noqa: BLE001
        return 1, {"verdict": "INTERNAL_ERROR"}
    if not isinstance(stage_desc, dict):
        return 1, {"verdict": "INTERNAL_ERROR"}

    bundle_hash = stage_desc.get("bundle_hash")
    if not isinstance(bundle_hash, str) or not _is_hex_hash(bundle_hash):
        return 1, {"verdict": "INTERNAL_ERROR"}

    active_dir = os.path.join(meta_core_root, ACTIVE_DIRNAME)
    os.makedirs(active_dir, exist_ok=True)
    active_next_path = os.path.join(active_dir, ACTIVE_NEXT_BUNDLE_FILENAME)
    try:
        atomic_write_text(active_next_path, bundle_hash + "\n")
        if os.environ.get(FAILPOINT_ENV) == FAILPOINT_AFTER_NEXT_WRITE:
            raise InternalError("failpoint AFTER_NEXT_WRITE triggered")
        commit_code, commit_out = commit_staged(meta_core_root, stage_path, receipt_path)
    except InternalError:
        return 1, {"verdict": "INTERNAL_ERROR"}

    if commit_code != 0:
        return commit_code, commit_out

    ledger_path = os.path.join(active_dir, LEDGER_DIRNAME, LEDGER_LOG_FILENAME)
    prev_seq, prev_entry_hash = read_last_entry(ledger_path)
    readiness_hash = hashlib.sha256(readiness_raw).hexdigest()
    entry = make_regime_upgrade_entry(
        active_bundle_hash=bundle_hash,
        readiness_receipt_hash=readiness_hash,
        tier_a_pass=tier_a_pass,
        tier_b_pass=tier_b_pass,
        runtime_tier_b_pass=runtime_tier_b_pass,
        prev_seq=prev_seq,
        prev_entry_hash=prev_entry_hash,
    )
    append_entry_crash_safe(ledger_path, entry)
    out = dict(commit_out)
    out["regime_upgrade_b"] = True
    out["reason_code"] = "READY"
    return 0, out


__all__ = ["commit_staged_regime_upgrade"]
