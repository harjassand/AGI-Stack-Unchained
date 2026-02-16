import hashlib
import json
import os
import shutil
from typing import Any, Dict, Tuple

import gcj1_min
from atomic_fs import atomic_write_text
from constants import (
    ACTIVE_BUNDLE_FILENAME,
    ACTIVE_DIRNAME,
    FAILPOINT_AFTER_PREV_WRITE,
    FAILPOINT_ENV,
    LEDGER_DIRNAME,
    LEDGER_LOG_FILENAME,
    NULL_BUNDLE_HASH,
    PREV_ACTIVE_BUNDLE_FILENAME,
    RECEIPT_FILENAME,
    STAGE_BUNDLES_DIRNAME,
    STAGE_DIRNAME,
)
from errors import InternalError
from hashing import (
    bundle_hash as compute_bundle_hash,
    manifest_hash,
    migration_hash,
    proof_bundle_hash,
    ruleset_hash,
    state_schema_hash,
    toolchain_merkle_root,
)
from ledger import append_entry_crash_safe, make_commit_entry, make_rollback_entry, read_last_entry
from store import store_bundle
from verifier_client import get_kernel_hash, get_meta_hash, run_verify


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


def _stage_dir(meta_core_root: str, bundle_hash: str) -> str:
    return os.path.join(meta_core_root, STAGE_DIRNAME, STAGE_BUNDLES_DIRNAME, bundle_hash)


def _read_pointer(path: str, required: bool) -> str:
    if not os.path.isfile(path):
        if required:
            raise InternalError("active pointer missing")
        return NULL_BUNDLE_HASH
    with open(path, "r", encoding="utf-8") as f:
        data = f.read()
    lines = data.splitlines(True)
    if len(lines) != 1 or not lines[0].endswith("\n"):
        raise InternalError("active pointer invalid")
    value = lines[0][:-1]
    if not _is_hex_hash(value):
        raise InternalError("active pointer invalid")
    return value


def stage_bundle(meta_core_root: str, bundle_dir: str, work_dir: str) -> Tuple[int, Dict[str, Any]]:
    if not os.path.isabs(meta_core_root) or not os.path.isabs(bundle_dir) or not os.path.isabs(work_dir):
        return 1, {"verdict": "INTERNAL_ERROR"}

    try:
        manifest_path = os.path.join(bundle_dir, "constitution.manifest.json")
        manifest = _read_json(manifest_path)
        if not isinstance(manifest, dict):
            return 2, {"verdict": "INVALID"}
    except Exception:  # noqa: BLE001
        return 2, {"verdict": "INVALID"}

    try:
        declared_bundle_hash = manifest.get("bundle_hash")
        declared_parent_hash = manifest.get("parent_bundle_hash", "")
        declared_ruleset_hash = manifest.get("ruleset_hash")
        declared_migration_hash = manifest.get("migration_hash")
        declared_state_schema_hash = manifest.get("state_schema_hash")
        declared_toolchain_root = manifest.get("toolchain_merkle_root")
        declared_proof_hash = manifest.get("proofs", {}).get("proof_bundle_hash")
        declared_meta_hash = manifest.get("meta_hash")
        declared_kernel_hash = manifest.get("kernel_hash")
    except Exception:  # noqa: BLE001
        return 2, {"verdict": "INVALID"}

    if not isinstance(declared_parent_hash, str):
        return 2, {"verdict": "INVALID"}
    if declared_parent_hash and not _is_hex_hash(declared_parent_hash):
        return 2, {"verdict": "INVALID"}

    try:
        expected_meta_hash = get_meta_hash(meta_core_root)
        expected_kernel_hash = get_kernel_hash(meta_core_root)
    except InternalError:
        return 1, {"verdict": "INTERNAL_ERROR"}

    computed_manifest_hash = manifest_hash(manifest)
    computed_ruleset_hash = ruleset_hash(bundle_dir)
    computed_proof_hash = proof_bundle_hash(bundle_dir)
    computed_migration_hash = migration_hash(bundle_dir)
    computed_state_schema_hash = state_schema_hash(meta_core_root)
    computed_toolchain_root = toolchain_merkle_root(meta_core_root)
    computed_bundle_hash = compute_bundle_hash(
        computed_manifest_hash,
        computed_ruleset_hash,
        computed_proof_hash,
        computed_migration_hash,
        computed_state_schema_hash,
        computed_toolchain_root,
    )

    if declared_bundle_hash != computed_bundle_hash:
        return 2, {"verdict": "INVALID"}
    if declared_ruleset_hash != computed_ruleset_hash:
        return 2, {"verdict": "INVALID"}
    if declared_proof_hash != computed_proof_hash:
        return 2, {"verdict": "INVALID"}
    if declared_migration_hash != computed_migration_hash:
        return 2, {"verdict": "INVALID"}
    if declared_state_schema_hash != computed_state_schema_hash:
        return 2, {"verdict": "INVALID"}
    if declared_toolchain_root != computed_toolchain_root:
        return 2, {"verdict": "INVALID"}

    if not isinstance(declared_meta_hash, str) or declared_meta_hash != expected_meta_hash:
        return 2, {"verdict": "INVALID"}
    if not isinstance(declared_kernel_hash, str) or declared_kernel_hash != expected_kernel_hash:
        return 2, {"verdict": "INVALID"}

    stage_dir = _stage_dir(meta_core_root, computed_bundle_hash)
    if not os.path.isdir(stage_dir):
        os.makedirs(os.path.dirname(stage_dir), exist_ok=True)
        shutil.copytree(bundle_dir, stage_dir)

    stage_desc = {
        "format": "meta_core_stage_v1",
        "schema_version": "1",
        "bundle_hash": computed_bundle_hash,
        "parent_bundle_hash": declared_parent_hash,
        "manifest_hash": computed_manifest_hash,
        "ruleset_hash": computed_ruleset_hash,
        "proof_bundle_hash": computed_proof_hash,
        "migration_hash": computed_migration_hash,
        "state_schema_hash": computed_state_schema_hash,
        "toolchain_merkle_root": computed_toolchain_root,
        "meta_hash": declared_meta_hash,
        "kernel_hash": declared_kernel_hash,
    }

    os.makedirs(work_dir, exist_ok=True)
    stage_path = os.path.join(work_dir, "stage.json")
    atomic_write_text(stage_path, gcj1_min.dumps(stage_desc) + "\n")

    return 0, {"verdict": "STAGED", "stage_path": stage_path, "bundle_hash": computed_bundle_hash}


def verify_staged(meta_core_root: str, stage_path: str, receipt_out_path: str) -> Tuple[int, Dict[str, Any]]:
    if not os.path.isabs(meta_core_root) or not os.path.isabs(stage_path) or not os.path.isabs(receipt_out_path):
        return 1, {"verdict": "INTERNAL_ERROR"}
    try:
        stage_desc = _read_json(stage_path)
    except Exception:  # noqa: BLE001
        return 1, {"verdict": "INTERNAL_ERROR"}
    if not isinstance(stage_desc, dict):
        return 1, {"verdict": "INTERNAL_ERROR"}

    bundle_hash = stage_desc.get("bundle_hash")
    parent_hash = stage_desc.get("parent_bundle_hash", "")
    if not isinstance(bundle_hash, str) or not _is_hex_hash(bundle_hash):
        return 1, {"verdict": "INTERNAL_ERROR"}
    if not isinstance(parent_hash, str):
        return 1, {"verdict": "INTERNAL_ERROR"}

    bundle_dir = _stage_dir(meta_core_root, bundle_hash)
    if not os.path.isdir(bundle_dir):
        return 1, {"verdict": "INTERNAL_ERROR"}

    parent_dir = None
    if parent_hash:
        candidate_parent = os.path.join(meta_core_root, "store", "bundles", parent_hash)
        if not os.path.isdir(candidate_parent):
            return 2, {"verdict": "INVALID"}
        parent_dir = candidate_parent

    exit_code, receipt_bytes = run_verify(
        meta_core_root,
        bundle_dir,
        parent_dir,
        receipt_out_path,
    )
    if exit_code != 0:
        return exit_code, {"verdict": "INVALID" if exit_code == 2 else "INTERNAL_ERROR"}

    try:
        receipt = json.loads(receipt_bytes.decode("utf-8"))
        receipt_bundle_hash = receipt.get("bundle_hash")
    except Exception:  # noqa: BLE001
        return 1, {"verdict": "INTERNAL_ERROR"}
    if receipt_bundle_hash != bundle_hash:
        return 1, {"verdict": "INTERNAL_ERROR"}

    return 0, {"verdict": "VERIFIED", "receipt_out": receipt_out_path}


def canary_staged(meta_core_root: str, stage_path: str, work_dir: str) -> Tuple[int, Dict[str, Any]]:
    if not os.path.isabs(meta_core_root) or not os.path.isabs(stage_path) or not os.path.isabs(work_dir):
        return 1, {"verdict": "INTERNAL_ERROR"}
    try:
        stage_desc = _read_json(stage_path)
    except Exception:  # noqa: BLE001
        return 1, {"verdict": "INTERNAL_ERROR"}
    if not isinstance(stage_desc, dict):
        return 1, {"verdict": "INTERNAL_ERROR"}

    bundle_hash = stage_desc.get("bundle_hash")
    if not isinstance(bundle_hash, str) or not _is_hex_hash(bundle_hash):
        return 1, {"verdict": "INTERNAL_ERROR"}
    toolchain_root = stage_desc.get("toolchain_merkle_root")
    if not isinstance(toolchain_root, str) or not _is_hex_hash(toolchain_root):
        return 1, {"verdict": "INTERNAL_ERROR"}
    parent_hash = stage_desc.get("parent_bundle_hash", "")
    if not isinstance(parent_hash, str):
        return 1, {"verdict": "INTERNAL_ERROR"}
    if parent_hash and not _is_hex_hash(parent_hash):
        return 1, {"verdict": "INTERNAL_ERROR"}
    parent_hash = stage_desc.get("parent_bundle_hash", "")
    if not isinstance(parent_hash, str):
        return 1, {"verdict": "INTERNAL_ERROR"}

    bundle_dir = _stage_dir(meta_core_root, bundle_hash)
    if not os.path.isdir(bundle_dir):
        return 1, {"verdict": "INTERNAL_ERROR"}

    # Recompute hashes to ensure determinism.
    manifest = _read_json(os.path.join(bundle_dir, "constitution.manifest.json"))
    recomputed_manifest_hash = manifest_hash(manifest)
    recomputed_ruleset_hash = ruleset_hash(bundle_dir)
    recomputed_proof_hash = proof_bundle_hash(bundle_dir)
    recomputed_migration_hash = migration_hash(bundle_dir)
    recomputed_state_schema_hash = state_schema_hash(meta_core_root)
    recomputed_toolchain_root = toolchain_merkle_root(meta_core_root)
    recomputed_bundle_hash = compute_bundle_hash(
        recomputed_manifest_hash,
        recomputed_ruleset_hash,
        recomputed_proof_hash,
        recomputed_migration_hash,
        recomputed_state_schema_hash,
        recomputed_toolchain_root,
    )

    if stage_desc.get("manifest_hash") != recomputed_manifest_hash:
        return 2, {"verdict": "INVALID"}
    if stage_desc.get("ruleset_hash") != recomputed_ruleset_hash:
        return 2, {"verdict": "INVALID"}
    if stage_desc.get("proof_bundle_hash") != recomputed_proof_hash:
        return 2, {"verdict": "INVALID"}
    if stage_desc.get("migration_hash") != recomputed_migration_hash:
        return 2, {"verdict": "INVALID"}
    if stage_desc.get("state_schema_hash") != recomputed_state_schema_hash:
        return 2, {"verdict": "INVALID"}
    if stage_desc.get("toolchain_merkle_root") != recomputed_toolchain_root:
        return 2, {"verdict": "INVALID"}
    if stage_desc.get("bundle_hash") != recomputed_bundle_hash:
        return 2, {"verdict": "INVALID"}

    parent_dir = None
    if parent_hash:
        candidate_parent = os.path.join(meta_core_root, "store", "bundles", parent_hash)
        if not os.path.isdir(candidate_parent):
            return 2, {"verdict": "INVALID"}
        parent_dir = candidate_parent

    receipt_path = os.path.join(work_dir, "canary_receipt.json")
    exit_code, _ = run_verify(meta_core_root, bundle_dir, parent_dir, receipt_path)
    if exit_code != 0:
        return exit_code, {"verdict": "INVALID" if exit_code == 2 else "INTERNAL_ERROR"}

    return 0, {"verdict": "CANARY_OK"}


def commit_staged(meta_core_root: str, stage_path: str, receipt_path: str) -> Tuple[int, Dict[str, Any]]:
    if not os.path.isabs(meta_core_root) or not os.path.isabs(stage_path) or not os.path.isabs(receipt_path):
        return 1, {"verdict": "INTERNAL_ERROR"}
    try:
        stage_desc = _read_json(stage_path)
    except Exception:  # noqa: BLE001
        return 1, {"verdict": "INTERNAL_ERROR"}
    if not isinstance(stage_desc, dict):
        return 1, {"verdict": "INTERNAL_ERROR"}

    bundle_hash = stage_desc.get("bundle_hash")
    if not isinstance(bundle_hash, str) or not _is_hex_hash(bundle_hash):
        return 1, {"verdict": "INTERNAL_ERROR"}

    parent_hash = stage_desc.get("parent_bundle_hash", "")
    if not isinstance(parent_hash, str):
        return 1, {"verdict": "INTERNAL_ERROR"}
    if parent_hash and not _is_hex_hash(parent_hash):
        return 1, {"verdict": "INTERNAL_ERROR"}

    toolchain_root = stage_desc.get("toolchain_merkle_root")
    if not isinstance(toolchain_root, str) or not _is_hex_hash(toolchain_root):
        return 1, {"verdict": "INTERNAL_ERROR"}

    bundle_dir = _stage_dir(meta_core_root, bundle_hash)
    if not os.path.isdir(bundle_dir):
        return 1, {"verdict": "INTERNAL_ERROR"}

    try:
        with open(receipt_path, "rb") as f:
            receipt_bytes = f.read()
    except OSError:
        return 1, {"verdict": "INTERNAL_ERROR"}
    receipt_hash = hashlib.sha256(receipt_bytes).hexdigest()

    try:
        receipt = json.loads(receipt_bytes.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return 1, {"verdict": "INTERNAL_ERROR"}
    if receipt.get("bundle_hash") != bundle_hash:
        return 1, {"verdict": "INTERNAL_ERROR"}

    active_dir = os.path.join(meta_core_root, ACTIVE_DIRNAME)
    os.makedirs(active_dir, exist_ok=True)
    active_path = os.path.join(active_dir, ACTIVE_BUNDLE_FILENAME)
    prev_path = os.path.join(active_dir, PREV_ACTIVE_BUNDLE_FILENAME)

    old_hash = _read_pointer(active_path, required=False)
    expected_parent = parent_hash if parent_hash else NULL_BUNDLE_HASH
    if old_hash != expected_parent:
        return 2, {"verdict": "INVALID"}
    store_bundle(meta_core_root, bundle_hash, bundle_dir, receipt_bytes)

    atomic_write_text(prev_path, old_hash + "\n")
    if os.environ.get(FAILPOINT_ENV) == FAILPOINT_AFTER_PREV_WRITE:
        raise InternalError("failpoint AFTER_PREV_WRITE triggered")
    atomic_write_text(active_path, bundle_hash + "\n")

    ledger_dir = os.path.join(active_dir, LEDGER_DIRNAME)
    ledger_path = os.path.join(ledger_dir, LEDGER_LOG_FILENAME)
    prev_seq, prev_entry_hash = read_last_entry(ledger_path)
    entry = make_commit_entry(
        bundle_hash,
        old_hash,
        receipt_hash,
        get_meta_hash(meta_core_root),
        get_kernel_hash(meta_core_root),
        toolchain_root,
        prev_seq,
        prev_entry_hash,
    )
    append_entry_crash_safe(ledger_path, entry)

    return 0, {"verdict": "COMMITTED", "active_bundle_hash": bundle_hash}


def rollback_active(meta_core_root: str, reason: str | None = None) -> Tuple[int, Dict[str, Any]]:
    if not os.path.isabs(meta_core_root):
        return 1, {"verdict": "INTERNAL_ERROR"}

    active_dir = os.path.join(meta_core_root, ACTIVE_DIRNAME)
    active_path = os.path.join(active_dir, ACTIVE_BUNDLE_FILENAME)
    prev_path = os.path.join(active_dir, PREV_ACTIVE_BUNDLE_FILENAME)

    try:
        old_active = _read_pointer(active_path, required=True)
        prev_active = _read_pointer(prev_path, required=True)
    except InternalError:
        return 1, {"verdict": "INTERNAL_ERROR"}

    if prev_active == NULL_BUNDLE_HASH:
        return 2, {"verdict": "INVALID"}

    atomic_write_text(prev_path, old_active + "\n")
    atomic_write_text(active_path, prev_active + "\n")

    receipt_path = os.path.join(
        meta_core_root, "store", "bundles", prev_active, RECEIPT_FILENAME
    )
    try:
        with open(receipt_path, "rb") as f:
            receipt_bytes = f.read()
    except OSError:
        return 1, {"verdict": "INTERNAL_ERROR"}
    receipt_hash = hashlib.sha256(receipt_bytes).hexdigest()

    ledger_dir = os.path.join(active_dir, LEDGER_DIRNAME)
    ledger_path = os.path.join(ledger_dir, LEDGER_LOG_FILENAME)
    prev_seq, prev_entry_hash = read_last_entry(ledger_path)
    entry = make_rollback_entry(
        prev_active,
        old_active,
        receipt_hash,
        get_meta_hash(meta_core_root),
        get_kernel_hash(meta_core_root),
        toolchain_merkle_root(meta_core_root),
        prev_seq,
        prev_entry_hash,
        reason,
    )
    append_entry_crash_safe(ledger_path, entry)

    return 0, {"verdict": "ROLLED_BACK", "active_bundle_hash": prev_active}
