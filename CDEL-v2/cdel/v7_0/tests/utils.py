from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Iterable

from cdel.v1_7r.canon import canon_bytes, load_canon_json, write_canon_json, write_jsonl_line
from cdel.v7_0.alignment_eval import compute_alignment_report_hash
from cdel.v7_0.daemon_ledger import compute_entry_hash
from cdel.v7_0.daemon_state import compute_daemon_id, compute_snapshot_hash
from cdel.v7_0.superego_ledger import compute_entry_hash as compute_superego_entry_hash
from cdel.v7_0.superego_policy import compute_policy_hash, compute_request_id


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def identities() -> tuple[str, str]:
    root = repo_root()
    lock = load_canon_json(root / "meta-core" / "meta_constitution" / "v7_0" / "immutable_core_lock_v1.json")
    icore_id = str(lock.get("core_id"))
    meta_hash = (root / "meta-core" / "meta_constitution" / "v7_0" / "META_HASH").read_text(encoding="utf-8").strip()
    return icore_id, meta_hash


def policy_hash() -> str:
    root = repo_root()
    policy = load_canon_json(root / "meta-core" / "meta_constitution" / "v7_0" / "superego_policy_v1.json")
    return compute_policy_hash(policy)


def write_alignment_pack(config_dir: Path, *, sealed_path: str, thresholds: dict[str, Any]) -> dict[str, Any]:
    icore_id, meta_hash = identities()
    pack: dict[str, Any] = {
        "schema_version": "rsi_alignment_pack_v1",
        "icore_id": icore_id,
        "meta_hash": meta_hash,
        "policy_hash": policy_hash(),
        "sealed_alignment_config": sealed_path,
        "clearance_thresholds": thresholds,
    }
    write_canon_json(config_dir / "rsi_alignment_pack_v1.json", pack)
    return pack


def write_daemon_pack(config_dir: Path, *, state_dir: Path, alignment_pack_path: str) -> dict[str, Any]:
    icore_id, meta_hash = identities()
    pack: dict[str, Any] = {
        "schema_version": "rsi_daemon_pack_v7",
        "icore_id": icore_id,
        "meta_hash": meta_hash,
        "daemon_id": "",
        "state_dir": str(state_dir),
        "control": {
            "stop": "control/STOP",
            "pause": "control/PAUSE",
            "enable_research": "control/ENABLE_RESEARCH",
        },
        "checkpoint_policy": {"every_ticks": 1, "retain_last_n": 2},
        "budgets": {"max_ticks_per_boot": 4, "max_work_units_per_day": 1000},
        "activities": [
            {
                "activity_kind": "NOOP_V1",
                "activity_id": "noop",
                "objective_class": "MAINTENANCE",
                "capabilities": ["FS_READ_WORKSPACE", "FS_WRITE_DAEMON_STATE", "NETWORK_NONE"],
            }
        ],
        "alignment": {
            "alignment_pack_path": alignment_pack_path,
            "policy_lock_path": "policy/superego_policy_lock_v1.json",
            "clearance_required_for_research_bounded": True,
            "clearance_required_for_boundless": True,
            "require_enable_research_file_for_boundless": True,
            "clearance_refresh_ticks": 2,
        },
    }
    pack["daemon_id"] = compute_daemon_id(pack)
    write_canon_json(config_dir / "rsi_daemon_pack_v7.json", pack)
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


def build_superego_entry(seq: int, tick: int, event_type: str, prev_hash: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    entry = {
        "seq": seq,
        "tick": tick,
        "event_type": event_type,
        "event_payload": payload or {},
        "prev_entry_hash": prev_hash,
        "entry_hash": "",
    }
    entry["entry_hash"] = compute_superego_entry_hash(entry)
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


def build_request(request: dict[str, Any]) -> dict[str, Any]:
    payload = dict(request)
    payload.setdefault("schema_version", "superego_action_request_v1")
    payload["request_id"] = compute_request_id(payload)
    return payload


def build_alignment_report(**kwargs: Any) -> dict[str, Any]:
    icore_id, meta_hash = identities()
    report = {
        "schema_version": "alignment_report_v1",
        "policy_hash": policy_hash(),
        "icore_id": icore_id,
        "meta_hash": meta_hash,
        "suite_id": "fixture",
        "hard_fail_count": 0,
        "hard_total": 4,
        "soft_pass_count": 2,
        "soft_total": 3,
        "align_score_num": 8,
        "align_score_den": 10,
        "meets_clearance": True,
        "evidence_hashes": [],
    }
    report.update(kwargs)
    return report


def build_clearance_receipt(report: dict[str, Any], *, ledger_head_hash: str, clearance_level: str = "BOUNDLESS") -> dict[str, Any]:
    icore_id, meta_hash = identities()
    return {
        "schema_version": "alignment_clearance_receipt_v1",
        "policy_hash": policy_hash(),
        "icore_id": icore_id,
        "meta_hash": meta_hash,
        "clearance_level": clearance_level,
        "issued_at_tick": 1,
        "alignment_report_hash": compute_alignment_report_hash(report),
        "ledger_head_hash": ledger_head_hash,
    }


def copy_policy(alignment_dir: Path) -> tuple[Path, Path]:
    root = repo_root()
    policy_src = root / "meta-core" / "meta_constitution" / "v7_0" / "superego_policy_v1.json"
    lock_src = root / "meta-core" / "meta_constitution" / "v7_0" / "superego_policy_lock_v1.json"
    policy_dst = alignment_dir / "policy" / "superego_policy_v1.json"
    lock_dst = alignment_dir / "policy" / "superego_policy_lock_v1.json"
    policy_dst.parent.mkdir(parents=True, exist_ok=True)
    policy_dst.write_text(policy_src.read_text(encoding="utf-8"), encoding="utf-8")
    lock_dst.write_text(lock_src.read_text(encoding="utf-8"), encoding="utf-8")
    return policy_dst, lock_dst


def write_alignment_artifacts(alignment_dir: Path, *, clearance_level: str = "BOUNDLESS") -> dict[str, str]:
    alignment_dir.mkdir(parents=True, exist_ok=True)
    copy_policy(alignment_dir)

    ledger_path = alignment_dir / "ledger" / "superego_ledger_v1.jsonl"
    entry = build_superego_entry(1, 0, "CLEARANCE_EMITTED", "GENESIS", {"note": "fixture"})
    write_ledger(ledger_path, [entry])

    report = build_alignment_report()
    report_path = alignment_dir / "reports" / "alignment_report_v1.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(report_path, report)

    receipt = build_clearance_receipt(report, ledger_head_hash=entry["entry_hash"], clearance_level=clearance_level)
    receipt_path = alignment_dir / "clearance" / "alignment_clearance_receipt_v1.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(receipt_path, receipt)

    return {
        "ledger": str(ledger_path),
        "report": str(report_path),
        "clearance": str(receipt_path),
    }


__all__ = [
    "build_alignment_report",
    "build_clearance_receipt",
    "build_entry",
    "build_request",
    "build_superego_entry",
    "copy_policy",
    "identities",
    "policy_hash",
    "repo_root",
    "write_alignment_artifacts",
    "write_alignment_pack",
    "write_daemon_pack",
    "write_ledger",
    "write_receipt",
    "write_snapshot",
]
