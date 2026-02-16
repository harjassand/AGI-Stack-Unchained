"""I/O helpers for omega daemon v18.0."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cdel.v18_0.omega_common_v1 import canon_hash_obj, fail, load_canon_dict, require_relpath, validate_schema
from cdel.v1_7r.canon import write_canon_json


_REQUIRED_FILES = [
    "rsi_omega_daemon_pack_v1.json",
    "omega_policy_ir_v1.json",
    "omega_capability_registry_v2.json",
    "omega_objectives_v1.json",
    "omega_runaway_config_v1.json",
    "omega_budgets_v1.json",
    "omega_allowlists_v1.json",
    "healthcheck_suitepack_v1.json",
    "baselines/baseline_metrics_v1.json",
    "goals/omega_goal_queue_v1.json",
]
_GOAL_QUEUE_BASE_PATH_REL = Path("goals") / "omega_goal_queue_v1.json"
_GOAL_QUEUE_EFFECTIVE_PATH_REL = Path("goals") / "omega_goal_queue_effective_v1.json"


def freeze_pack_config(*, campaign_pack: Path, config_dir: Path) -> tuple[dict[str, Any], str]:
    pack = load_canon_dict(campaign_pack)
    validate_schema(pack, "rsi_omega_daemon_pack_v1")
    if pack.get("schema_version") != "rsi_omega_daemon_pack_v1":
        fail("SCHEMA_FAIL")

    source_root = campaign_pack.parent
    for rel in _REQUIRED_FILES:
        src = source_root / rel
        if not src.exists() or not src.is_file():
            fail("MISSING_STATE_INPUT")
        payload = load_canon_dict(src)
        write_canon_json(config_dir / rel, payload)

    write_canon_json(config_dir / "rsi_omega_daemon_pack_v1.json", pack)
    return pack, canon_hash_obj(pack)


def _validate_goal_queue(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != "omega_goal_queue_v1":
        fail("SCHEMA_FAIL")
    goals = payload.get("goals")
    if not isinstance(goals, list):
        fail("SCHEMA_FAIL")
    for row in goals:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        goal_id = str(row.get("goal_id", "")).strip()
        capability_id = str(row.get("capability_id", "")).strip()
        status = str(row.get("status", "PENDING")).strip()
        if not goal_id or not capability_id or status not in {"PENDING", "DONE", "FAILED"}:
            fail("SCHEMA_FAIL")
    return payload


def load_goal_queue(config_dir: Path) -> tuple[dict[str, Any], str]:
    effective_path = config_dir / _GOAL_QUEUE_EFFECTIVE_PATH_REL
    if effective_path.exists():
        if not effective_path.is_file():
            fail("SCHEMA_FAIL")
        payload = _validate_goal_queue(load_canon_dict(effective_path))
        return payload, canon_hash_obj(payload)

    path = config_dir / _GOAL_QUEUE_BASE_PATH_REL
    payload = _validate_goal_queue(load_canon_dict(path))
    return payload, canon_hash_obj(payload)


def write_goal_queue_effective(config_dir: Path, payload: dict[str, Any]) -> tuple[Path, dict[str, Any], str]:
    out_payload = _validate_goal_queue(dict(payload))
    out_path = config_dir / _GOAL_QUEUE_EFFECTIVE_PATH_REL
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(out_path, out_payload)
    return out_path, out_payload, canon_hash_obj(out_payload)


__all__ = ["freeze_pack_config", "load_goal_queue", "write_goal_queue_effective"]
