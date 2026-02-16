"""Verifier for RSI Sovereign Persistence (v6.0, SP protocol v1)."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed
from ..v2_3.immutable_core import load_lock, validate_lock
from .daemon_checkpoint import compute_receipt_hash, load_receipt
from .daemon_ledger import load_daemon_ledger, validate_daemon_chain
from .daemon_state import compute_daemon_id, compute_snapshot_hash, load_snapshot


def _fail(reason: str) -> None:
    raise CanonError(reason)


def _meta_core_root() -> Path:
    env_override = Path(os.environ.get("META_CORE_ROOT", "")) if os.environ.get("META_CORE_ROOT") else None
    if env_override and env_override.exists():
        return env_override
    return Path(__file__).resolve().parents[3] / "meta-core"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _require_constants() -> dict[str, Any]:
    meta_root = _meta_core_root()
    constants_path = meta_root / "meta_constitution" / "v6_0" / "constants_v1.json"
    return load_canon_json(constants_path)


def _meta_identities() -> dict[str, str]:
    meta_root = _meta_core_root()
    meta_hash = _read_text(meta_root / "meta_constitution" / "v6_0" / "META_HASH")
    kernel_hash = _read_text(meta_root / "kernel" / "verifier" / "KERNEL_HASH")
    constants_hash = sha256_prefixed(canon_bytes(_require_constants()))
    return {
        "META_HASH": meta_hash,
        "KERNEL_HASH": kernel_hash,
        "constants_hash": constants_hash,
    }


def _load_pack(config_dir: Path) -> dict[str, Any]:
    pack_path = config_dir / "rsi_daemon_pack_v1.json"
    if not pack_path.exists():
        _fail("MISSING_ARTIFACT")
    pack = load_canon_json(pack_path)
    if not isinstance(pack, dict):
        _fail("SCHEMA_INVALID")
    if pack.get("schema_version") != "rsi_daemon_pack_v1":
        _fail("SCHEMA_INVALID")
    for key in ["icore_id", "meta_hash", "daemon_id", "state_dir", "control", "checkpoint_policy", "budgets", "activities"]:
        if key not in pack:
            _fail("SCHEMA_INVALID")
    return pack


def _require_str(obj: dict[str, Any], key: str) -> str:
    val = obj.get(key)
    if not isinstance(val, str):
        _fail("SCHEMA_INVALID")
    return val


def _require_int(obj: dict[str, Any], key: str) -> int:
    val = obj.get(key)
    if not isinstance(val, int):
        _fail("SCHEMA_INVALID")
    return val


def _validate_receipt_name(path: Path, receipt: dict[str, Any]) -> None:
    receipt_hash = compute_receipt_hash(receipt)
    name = f"sha256_{receipt_hash.split(':', 1)[1]}.{receipt.get('schema_version')}.json"
    if path.name != name:
        _fail("CANON_HASH_MISMATCH")


def _collect_snapshots(snapshot_dir: Path) -> dict[str, dict[str, Any]]:
    snapshots: dict[str, dict[str, Any]] = {}
    if not snapshot_dir.exists():
        _fail("MISSING_ARTIFACT")
    for path in snapshot_dir.glob("sha256_*.daemon_state_snapshot_v1.json"):
        snapshot = load_snapshot(path)
        snap_hash = compute_snapshot_hash(snapshot)
        expected = f"sha256_{snap_hash.split(':', 1)[1]}.daemon_state_snapshot_v1.json"
        if path.name != expected:
            _fail("CANON_HASH_MISMATCH")
        snapshots[snap_hash] = snapshot
    if not snapshots:
        _fail("MISSING_ARTIFACT")
    return snapshots


def _check_meta_drift_handling(entries: list[dict[str, Any]]) -> None:
    meta_idx = None
    pause_idx = None
    for idx, ev in enumerate(entries):
        if ev.get("event_type") == "META_DRIFT_DETECTED" and meta_idx is None:
            meta_idx = idx
        if meta_idx is not None and ev.get("event_type") == "PAUSED":
            pause_idx = idx
            break
    if meta_idx is None or pause_idx is None:
        _fail("META_DRIFT_UNHANDLED")
    for ev in entries[pause_idx + 1 :]:
        if ev.get("event_type") == "TICK_BEGIN":
            _fail("META_DRIFT_UNHANDLED")


def verify(state_dir: Path, *, mode: str) -> dict[str, Any]:
    constants = _require_constants()
    lock_rel = constants.get("IMMUTABLE_CORE_LOCK_REL")
    if not isinstance(lock_rel, str):
        _fail("IMMUTABLE_CORE_ATTESTATION_INVALID")

    repo_root = Path(__file__).resolve().parents[3]
    lock_path = repo_root / lock_rel
    if not lock_path.exists():
        _fail("MISSING_ARTIFACT")
    lock = load_lock(lock_path)
    try:
        validate_lock(lock)
    except Exception as exc:  # noqa: BLE001
        raise CanonError("IMMUTABLE_CORE_ATTESTATION_INVALID") from exc

    identities = _meta_identities()
    expected_icore = str(lock.get("core_id"))
    expected_meta = identities.get("META_HASH")

    daemon_root = state_dir.parent
    config_dir = daemon_root / "config"
    pack = _load_pack(config_dir)

    computed_daemon_id = compute_daemon_id(pack)
    if pack.get("daemon_id") != computed_daemon_id:
        _fail("CANON_HASH_MISMATCH")
    expected_daemon_id = pack.get("daemon_id")

    pack_state_dir = Path(_require_str(pack, "state_dir")).resolve()
    if pack_state_dir != state_dir.resolve():
        _fail("SCHEMA_INVALID")

    meta_drift = False
    if pack.get("icore_id") != expected_icore or pack.get("meta_hash") != expected_meta:
        meta_drift = True

    ledger_path = state_dir / "ledger" / "daemon_ledger_v1.jsonl"
    events = load_daemon_ledger(ledger_path)
    head_hash, last_tick, _last_seq = validate_daemon_chain(events)
    if not events:
        _fail("SCHEMA_INVALID")

    entry_by_hash = {ev.get("entry_hash"): ev for ev in events if isinstance(ev.get("entry_hash"), str)}

    snapshots = _collect_snapshots(state_dir / "snapshots")
    for snap in snapshots.values():
        if snap.get("daemon_id") != expected_daemon_id:
            _fail("SCHEMA_INVALID")
        if snap.get("icore_id") != expected_icore or snap.get("meta_hash") != expected_meta:
            meta_drift = True

    checkpoint_dir = state_dir / "checkpoints"
    checkpoint_receipts: list[dict[str, Any]] = []
    if checkpoint_dir.exists():
        for path in checkpoint_dir.glob("sha256_*.daemon_checkpoint_receipt_v1.json"):
            receipt = load_receipt(path, schema_version="daemon_checkpoint_receipt_v1", kind="CHECKPOINT")
            _validate_receipt_name(path, receipt)
            checkpoint_receipts.append(receipt)
    if not checkpoint_receipts:
        _fail("MISSING_ARTIFACT")

    for receipt in checkpoint_receipts:
        if receipt.get("daemon_id") != expected_daemon_id:
            _fail("SCHEMA_INVALID")
        if receipt.get("icore_id") != expected_icore or receipt.get("meta_hash") != expected_meta:
            meta_drift = True
        snapshot_hash = _require_str(receipt, "snapshot_hash")
        if snapshot_hash not in snapshots:
            _fail("MISSING_ARTIFACT")
        snapshot = snapshots[snapshot_hash]
        if snapshot.get("ledger_head_hash") != receipt.get("ledger_head_hash"):
            _fail("CANON_HASH_MISMATCH")
        if snapshot.get("tick") != receipt.get("tick"):
            _fail("CANON_HASH_MISMATCH")
        if snapshot.get("boot_count") != receipt.get("boot_count"):
            _fail("CANON_HASH_MISMATCH")
        ledger_head_hash = _require_str(receipt, "ledger_head_hash")
        entry = entry_by_hash.get(ledger_head_hash)
        if entry is None or entry.get("event_type") != "CHECKPOINT":
            _fail("DAEMON_CHECKPOINT_MISMATCH")

    boot_dir = state_dir / "boots"
    boot_receipts: list[dict[str, Any]] = []
    if boot_dir.exists():
        for path in boot_dir.glob("sha256_*.daemon_boot_receipt_v1.json"):
            receipt = load_receipt(path, schema_version="daemon_boot_receipt_v1", kind="BOOT")
            _validate_receipt_name(path, receipt)
            boot_receipts.append(receipt)
    if not boot_receipts:
        _fail("MISSING_ARTIFACT")

    boot_counts = sorted(int(r.get("boot_count", -1)) for r in boot_receipts)
    if not boot_counts or boot_counts[0] != 1 or boot_counts != list(range(1, len(boot_counts) + 1)):
        _fail("SCHEMA_INVALID")

    boot_events = [ev for ev in events if ev.get("event_type") == "BOOT"]
    if len(boot_events) != len(boot_receipts):
        _fail("SCHEMA_INVALID")

    for receipt in boot_receipts:
        if receipt.get("daemon_id") != expected_daemon_id:
            _fail("SCHEMA_INVALID")
        if receipt.get("icore_id") != expected_icore or receipt.get("meta_hash") != expected_meta:
            meta_drift = True
        ledger_head_hash = _require_str(receipt, "ledger_head_hash")
        entry = entry_by_hash.get(ledger_head_hash)
        if entry is None or entry.get("event_type") != "BOOT":
            _fail("SCHEMA_INVALID")
        euid = _require_int(receipt, "euid")
        if euid == 0:
            if any(ev.get("event_type") == "TICK_BEGIN" for ev in events):
                _fail("DAEMON_REFUSE_ROOT")
            if not any(ev.get("event_type") == "FATAL" for ev in events):
                _fail("DAEMON_REFUSE_ROOT")

    shutdown_dir = state_dir / "shutdowns"
    shutdown_receipts: list[dict[str, Any]] = []
    if shutdown_dir.exists():
        for path in shutdown_dir.glob("sha256_*.daemon_shutdown_receipt_v1.json"):
            receipt = load_receipt(path, schema_version="daemon_shutdown_receipt_v1", kind="SHUTDOWN")
            _validate_receipt_name(path, receipt)
            shutdown_receipts.append(receipt)

    for receipt in shutdown_receipts:
        if receipt.get("daemon_id") != expected_daemon_id:
            _fail("SCHEMA_INVALID")
        if receipt.get("icore_id") != expected_icore or receipt.get("meta_hash") != expected_meta:
            meta_drift = True
        ledger_head_hash = _require_str(receipt, "ledger_head_hash")
        entry = entry_by_hash.get(ledger_head_hash)
        if entry is None or entry.get("event_type") != "SHUTDOWN":
            _fail("SCHEMA_INVALID")

    if mode == "full":
        if not shutdown_receipts:
            _fail("MISSING_ARTIFACT")
        # Require a clean shutdown receipt matching the final ledger head.
        if not any(r.get("ledger_head_hash") == head_hash for r in shutdown_receipts):
            _fail("SCHEMA_INVALID")

    stop_path = state_dir / "control" / "STOP"
    if stop_path.exists():
        stop_idx = None
        shutdown_idx = None
        for idx, ev in enumerate(events):
            if ev.get("event_type") == "STOP_REQUESTED" and stop_idx is None:
                stop_idx = idx
            if ev.get("event_type") == "SHUTDOWN":
                shutdown_idx = idx
        if shutdown_idx is not None and (stop_idx is None or stop_idx > shutdown_idx):
            _fail("SCHEMA_INVALID")

    if meta_drift:
        _check_meta_drift_handling(events)

    return {
        "verdict": "VALID",
        "ledger_head_hash": head_hash,
        "last_tick": last_tick,
        "icore_id": expected_icore,
        "meta_hash": expected_meta,
        "mode": mode,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state_dir", required=True)
    parser.add_argument("--mode", choices=["prefix", "full"], default="full")
    args = parser.parse_args(argv)
    try:
        verify(Path(args.state_dir), mode=str(args.mode))
    except CanonError as exc:
        print(f"INVALID: {exc}")
        return 2
    print("VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
