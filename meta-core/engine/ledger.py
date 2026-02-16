import hashlib
import json
import os
from typing import Any, Dict, Tuple

import gcj1_min
from atomic_fs import fsync_dir
from constants import NULL_BUNDLE_HASH
from errors import InternalError


def _is_hex_hash(value: str) -> bool:
    if len(value) != 64:
        return False
    for ch in value:
        if ch not in "0123456789abcdef":
            return False
    return True


def _compute_entry_hash(entry_no_hash: Dict[str, Any]) -> str:
    payload = gcj1_min.dumps_bytes(entry_no_hash)
    return hashlib.sha256(payload).hexdigest()


def read_last_entry(log_path: str) -> Tuple[int, str]:
    if not os.path.isfile(log_path):
        return 0, NULL_BUNDLE_HASH
    try:
        with open(log_path, "rb") as f:
            data = f.read()
    except OSError as exc:
        raise InternalError("failed to read ledger log") from exc
    if data == b"":
        return 0, NULL_BUNDLE_HASH
    if not data.endswith(b"\n"):
        raise InternalError("ledger log missing trailing newline")
    lines = data.splitlines()
    if not lines:
        return 0, NULL_BUNDLE_HASH
    try:
        last = json.loads(lines[-1].decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise InternalError("failed to parse ledger entry") from exc
    if not isinstance(last, dict):
        raise InternalError("ledger entry must be an object")
    seq = last.get("seq")
    entry_hash = last.get("entry_hash")
    if not isinstance(seq, int):
        raise InternalError("ledger seq must be int")
    if not isinstance(entry_hash, str) or not _is_hex_hash(entry_hash):
        raise InternalError("ledger entry_hash invalid")
    return seq, entry_hash


def validate_chain(log_path: str) -> Tuple[int, str]:
    if not os.path.isfile(log_path):
        return 0, NULL_BUNDLE_HASH
    try:
        with open(log_path, "rb") as f:
            data = f.read()
    except OSError as exc:
        raise InternalError("failed to read ledger log") from exc
    if data == b"":
        return 0, NULL_BUNDLE_HASH
    if not data.endswith(b"\n"):
        raise InternalError("ledger log missing trailing newline")
    lines = data.splitlines()
    prev_hash = NULL_BUNDLE_HASH
    prev_seq = 0
    for line in lines:
        try:
            entry = json.loads(line.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise InternalError("failed to parse ledger entry") from exc
        if not isinstance(entry, dict):
            raise InternalError("ledger entry must be an object")
        seq = entry.get("seq")
        entry_hash = entry.get("entry_hash")
        prev_entry_hash = entry.get("prev_entry_hash")
        if not isinstance(seq, int):
            raise InternalError("ledger seq must be int")
        if seq != prev_seq + 1:
            raise InternalError("ledger seq not monotone")
        if not isinstance(prev_entry_hash, str) or not _is_hex_hash(prev_entry_hash):
            raise InternalError("ledger prev_entry_hash invalid")
        if prev_entry_hash != prev_hash:
            raise InternalError("ledger chain mismatch")
        if not isinstance(entry_hash, str) or not _is_hex_hash(entry_hash):
            raise InternalError("ledger entry_hash invalid")
        entry_no_hash = dict(entry)
        entry_no_hash.pop("entry_hash", None)
        expected = _compute_entry_hash(entry_no_hash)
        if entry_hash != expected:
            raise InternalError("ledger entry_hash mismatch")
        prev_hash = entry_hash
        prev_seq = seq
    return prev_seq, prev_hash


def make_commit_entry(
    active_bundle_hash: str,
    prev_active_bundle_hash: str,
    receipt_hash: str,
    meta_hash: str,
    kernel_hash: str,
    toolchain_merkle_root: str,
    prev_seq: int,
    prev_entry_hash: str,
) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "seq": prev_seq + 1,
        "action": "COMMIT",
        "active_bundle_hash": active_bundle_hash,
        "prev_active_bundle_hash": prev_active_bundle_hash,
        "receipt_hash": receipt_hash,
        "meta_hash": meta_hash,
        "kernel_hash": kernel_hash,
        "toolchain_merkle_root": toolchain_merkle_root,
        "prev_entry_hash": prev_entry_hash,
    }
    entry["entry_hash"] = _compute_entry_hash(entry)
    return entry


def make_rollback_entry(
    active_bundle_hash: str,
    prev_active_bundle_hash: str,
    receipt_hash: str,
    meta_hash: str,
    kernel_hash: str,
    toolchain_merkle_root: str,
    prev_seq: int,
    prev_entry_hash: str,
    reason: str | None = None,
) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "seq": prev_seq + 1,
        "action": "ROLLBACK",
        "active_bundle_hash": active_bundle_hash,
        "prev_active_bundle_hash": prev_active_bundle_hash,
        "receipt_hash": receipt_hash,
        "meta_hash": meta_hash,
        "kernel_hash": kernel_hash,
        "toolchain_merkle_root": toolchain_merkle_root,
        "prev_entry_hash": prev_entry_hash,
    }
    if reason is not None:
        entry["reason"] = reason
    entry["entry_hash"] = _compute_entry_hash(entry)
    return entry


def append_entry_crash_safe(log_path: str, entry_dict: Dict[str, Any]) -> None:
    dir_path = os.path.dirname(log_path) or "."
    os.makedirs(dir_path, exist_ok=True)
    existing = b""
    if os.path.isfile(log_path):
        try:
            with open(log_path, "rb") as f:
                existing = f.read()
        except OSError as exc:
            raise InternalError("failed to read ledger log") from exc
        if existing and not existing.endswith(b"\n"):
            raise InternalError("ledger log missing trailing newline")

    line = gcj1_min.dumps_bytes(entry_dict) + b"\n"
    tmp_path = log_path + ".tmp"
    try:
        with open(tmp_path, "wb") as f:
            if existing:
                f.write(existing)
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, log_path)
        fsync_dir(dir_path)
    except OSError as exc:
        raise InternalError("failed to write ledger log") from exc
