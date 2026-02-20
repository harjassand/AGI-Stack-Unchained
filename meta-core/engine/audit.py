import fcntl
import hashlib
import json
import os
from typing import Tuple, Dict, Any

from constants import (
    ACTIVE_DIRNAME,
    ACTIVE_NEXT_BUNDLE_FILENAME,
    ACTIVE_BUNDLE_FILENAME,
    PREV_ACTIVE_BUNDLE_FILENAME,
    STORE_DIRNAME,
    STORE_BUNDLES_DIRNAME,
    RECEIPT_FILENAME,
    NULL_BUNDLE_HASH,
    LEDGER_DIRNAME,
    LEDGER_LOG_FILENAME,
)
from errors import InternalError
from ledger import validate_chain
from verifier_client import run_verify, get_kernel_hash, get_meta_hash


def _is_hex_hash(value: str) -> bool:
    if len(value) != 64:
        return False
    for ch in value:
        if ch not in "0123456789abcdef":
            return False
    return True


def _read_active_pointer_required(path: str) -> str:
    if not os.path.isfile(path):
        raise ValueError("active pointer missing")
    with open(path, "r", encoding="utf-8") as f:
        data = f.read()
    lines = data.splitlines(True)
    if len(lines) != 1 or not lines[0].endswith("\n"):
        raise ValueError("active pointer invalid")
    value = lines[0][:-1]
    if not _is_hex_hash(value):
        raise ValueError("active pointer invalid")
    return value


def _read_manifest_parent(bundle_dir: str) -> str:
    manifest_path = os.path.join(bundle_dir, "constitution.manifest.json")
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            obj = json.load(f)
    except OSError as exc:
        raise ValueError("manifest missing") from exc
    except Exception as exc:  # noqa: BLE001
        raise ValueError("manifest invalid") from exc
    if not isinstance(obj, dict):
        raise ValueError("manifest invalid")
    parent_hash = obj.get("parent_bundle_hash")
    if parent_hash is None or not isinstance(parent_hash, str):
        raise ValueError("manifest parent invalid")
    if parent_hash == "":
        return NULL_BUNDLE_HASH
    if not _is_hex_hash(parent_hash):
        raise ValueError("manifest parent invalid")
    return parent_hash


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def audit_active(meta_core_root: str) -> Tuple[int, Dict[str, Any]]:
    active_dir = os.path.join(meta_core_root, ACTIVE_DIRNAME)
    lock_path = os.path.join(active_dir, "LOCK")
    os.makedirs(active_dir, exist_ok=True)

    lock_fd = open(lock_path, "a+")
    fcntl.flock(lock_fd, fcntl.LOCK_EX)

    try:
        try:
            active_path = os.path.join(active_dir, ACTIVE_BUNDLE_FILENAME)
            try:
                active_hash = _read_active_pointer_required(active_path)
            except ValueError:
                return 2, _invalid_audit()

            prev_path = os.path.join(active_dir, PREV_ACTIVE_BUNDLE_FILENAME)
            prev_hash = NULL_BUNDLE_HASH
            if os.path.isfile(prev_path):
                try:
                    prev_hash = _read_active_pointer_required(prev_path)
                except ValueError:
                    return 2, _invalid_audit()

            active_next_path = os.path.join(active_dir, ACTIVE_NEXT_BUNDLE_FILENAME)
            active_next_hash = active_hash
            if os.path.isfile(active_next_path):
                try:
                    active_next_hash = _read_active_pointer_required(active_next_path)
                except ValueError:
                    return 2, _invalid_audit()
                if active_next_hash != active_hash:
                    return 2, _invalid_audit()

            store_bundle_dir = os.path.join(
                meta_core_root, STORE_DIRNAME, STORE_BUNDLES_DIRNAME, active_hash
            )
            if not os.path.isdir(store_bundle_dir):
                return 2, _invalid_audit()

            stored_receipt_path = os.path.join(store_bundle_dir, RECEIPT_FILENAME)
            if not os.path.isfile(stored_receipt_path):
                return 2, _invalid_audit()

            try:
                with open(stored_receipt_path, "rb") as f:
                    stored_receipt_bytes = f.read()
            except OSError as exc:
                raise InternalError("failed to read stored receipt") from exc

            try:
                parent_hash = _read_manifest_parent(store_bundle_dir)
            except ValueError:
                return 2, _invalid_audit()

            parent_dir = None
            if parent_hash != NULL_BUNDLE_HASH:
                candidate_parent = os.path.join(
                    meta_core_root, STORE_DIRNAME, STORE_BUNDLES_DIRNAME, parent_hash
                )
                if not os.path.isdir(candidate_parent):
                    return 2, _invalid_audit()
                parent_dir = candidate_parent

            tmp_dir = os.path.join(active_dir, "tmp")
            os.makedirs(tmp_dir, exist_ok=True)
            receipt_out = os.path.join(tmp_dir, "audit_receipt.json")

            exit_code, new_receipt_bytes = run_verify(
                meta_core_root, store_bundle_dir, parent_dir, receipt_out
            )
            if exit_code != 0:
                return 2, _invalid_audit()

            receipt_sha256_new = _sha256_hex(new_receipt_bytes)
            receipt_sha256_stored = _sha256_hex(stored_receipt_bytes)
            if receipt_sha256_new != receipt_sha256_stored:
                return 2, _invalid_audit()

            kernel_hash = get_kernel_hash(meta_core_root)
            meta_hash = get_meta_hash(meta_core_root)

            try:
                manifest_path = os.path.join(store_bundle_dir, "constitution.manifest.json")
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
            except Exception:  # noqa: BLE001
                return 2, _invalid_audit()
            if not isinstance(manifest, dict):
                return 2, _invalid_audit()

            ruleset_hash = manifest.get("ruleset_hash")
            toolchain_merkle_root = manifest.get("toolchain_merkle_root")
            if not isinstance(ruleset_hash, str) or not _is_hex_hash(ruleset_hash):
                return 2, _invalid_audit()
            if not isinstance(toolchain_merkle_root, str) or not _is_hex_hash(toolchain_merkle_root):
                return 2, _invalid_audit()

            ledger_path = os.path.join(active_dir, LEDGER_DIRNAME, LEDGER_LOG_FILENAME)
            _, ledger_head_hash = validate_chain(ledger_path)

            out = {
                "verdict": "OK",
                "active_bundle_hash": active_hash,
                "prev_active_bundle_hash": "" if prev_hash == NULL_BUNDLE_HASH else prev_hash,
                "active_next_bundle_hash": active_next_hash,
                "kernel_hash": kernel_hash,
                "meta_hash": meta_hash,
                "ruleset_hash": ruleset_hash,
                "toolchain_merkle_root": toolchain_merkle_root,
                "ledger_head_hash": ledger_head_hash,
            }
            return 0, out
        except InternalError:
            return 1, _internal_audit()
        except Exception:  # noqa: BLE001
            return 1, _internal_audit()
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            lock_fd.close()


def _invalid_audit() -> Dict[str, Any]:
    return {
        "verdict": "INVALID",
        "active_bundle_hash": "",
        "prev_active_bundle_hash": "",
        "active_next_bundle_hash": "",
        "kernel_hash": "",
        "meta_hash": "",
        "ruleset_hash": "",
        "toolchain_merkle_root": "",
        "ledger_head_hash": "",
    }


def _internal_audit() -> Dict[str, Any]:
    return {
        "verdict": "INTERNAL_ERROR",
        "active_bundle_hash": "",
        "prev_active_bundle_hash": "",
        "active_next_bundle_hash": "",
        "kernel_hash": "",
        "meta_hash": "",
        "ruleset_hash": "",
        "toolchain_merkle_root": "",
        "ledger_head_hash": "",
    }
