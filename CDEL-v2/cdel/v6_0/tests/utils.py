from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Iterable

from cdel.v1_7r.canon import canon_bytes, load_canon_json, write_canon_json, write_jsonl_line
from cdel.v6_0.daemon_ledger import compute_entry_hash
from cdel.v6_0.daemon_state import compute_daemon_id, compute_snapshot_hash


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def identities() -> tuple[str, str]:
    root = repo_root()
    lock = load_canon_json(root / "meta-core" / "meta_constitution" / "v6_0" / "immutable_core_lock_v1.json")
    icore_id = str(lock.get("core_id"))
    meta_hash = (root / "meta-core" / "meta_constitution" / "v6_0" / "META_HASH").read_text(encoding="utf-8").strip()
    return icore_id, meta_hash


def write_pack(config_dir: Path, *, state_dir: Path, activities: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    icore_id, meta_hash = identities()
    pack: dict[str, Any] = {
        "schema_version": "rsi_daemon_pack_v1",
        "icore_id": icore_id,
        "meta_hash": meta_hash,
        "daemon_id": "",
        "state_dir": str(state_dir),
        "control": {"stop": "control/STOP", "pause": "control/PAUSE"},
        "checkpoint_policy": {"every_ticks": 1, "retain_last_n": 2},
        "budgets": {"max_ticks_per_boot": 4, "max_work_units_per_day": 1000},
        "activities": activities or [{"activity_kind": "NOOP_V1", "activity_id": "noop"}],
    }
    pack["daemon_id"] = compute_daemon_id(pack)
    write_canon_json(config_dir / "rsi_daemon_pack_v1.json", pack)
    return pack


def build_entry(seq: int, tick: int, event_type: str, prev_hash: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    entry = {
        "seq": seq,
        "tick": tick,
        "event_type": event_type,
        "event_payload": payload or {},
        "prev_entry_hash": prev_hash,
        "entry_hash": "",
    }
    entry["entry_hash"] = compute_entry_hash(entry)
    return entry


def write_ledger(path: Path, entries: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    for entry in entries:
        write_jsonl_line(path, entry)


def write_snapshot(snapshot_dir: Path, snapshot: dict[str, Any]) -> str:
    snap_hash = compute_snapshot_hash(snapshot)
    name = f"sha256_{snap_hash.split(':', 1)[1]}.daemon_state_snapshot_v1.json"
    write_canon_json(snapshot_dir / name, snapshot)
    return snap_hash


def write_receipt(receipt_dir: Path, receipt: dict[str, Any]) -> str:
    receipt_hash = hashlib.sha256(canon_bytes(receipt)).hexdigest()
    name = f"sha256_{receipt_hash}.{receipt['schema_version']}.json"
    write_canon_json(receipt_dir / name, receipt)
    return f"sha256:{receipt_hash}"


__all__ = [
    "build_entry",
    "identities",
    "repo_root",
    "write_ledger",
    "write_pack",
    "write_receipt",
    "write_snapshot",
]
