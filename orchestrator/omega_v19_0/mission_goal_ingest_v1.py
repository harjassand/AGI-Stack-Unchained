"""Deterministic mission request -> goal queue ingestion for v19 long runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cdel.v18_0.omega_common_v1 import canon_hash_obj
from cdel.v19_0.common_v1 import validate_schema as validate_schema_v19

_PRIORITY_PREFIX: dict[str, str] = {
    "HIGH": "goal_auto_00_mission_",
    "MED": "goal_auto_10_mission_",
    "LOW": "goal_auto_90_mission_",
}

_MISSION_TAG_TO_CAPABILITY_IDS: dict[str, tuple[str, ...]] = {
    "bootstrap": ("RSI_POLYMATH_BOOTSTRAP_DOMAIN",),
    "code": ("RSI_SAS_CODE",),
    "conquer": ("RSI_POLYMATH_CONQUER_DOMAIN",),
    "epistemic": ("RSI_EPISTEMIC_REDUCE_V1",),
    "eudrs": ("RSI_EUDRS_U_TRAIN",),
    "explore": ("RSI_POLYMATH_SCOUT",),
    "metasearch": ("RSI_SAS_METASEARCH",),
    "native": ("RSI_OMEGA_NATIVE_MODULE",),
    "optimize": ("RSI_GE_SH1_OPTIMIZER",),
    "science": ("RSI_SAS_SCIENCE",),
    "sip": ("RSI_POLYMATH_SIP_INGESTION_L0",),
    "transpile": ("RSI_KNOWLEDGE_TRANSPILER",),
    "transpiler": ("RSI_KNOWLEDGE_TRANSPILER",),
}
_DOMAIN_TOKEN_TO_CAPABILITY_IDS: dict[str, tuple[str, ...]] = {
    "eudrs": ("RSI_EUDRS_U_TRAIN",),
    "math": ("RSI_SAS_METASEARCH",),
    "native": ("RSI_OMEGA_NATIVE_MODULE",),
    "science": ("RSI_SAS_SCIENCE",),
}
_MAPPING_TABLE_HASH = canon_hash_obj(
    {
        "mission_tag_map": {key: list(value) for key, value in sorted(_MISSION_TAG_TO_CAPABILITY_IDS.items())},
        "domain_token_map": {key: list(value) for key, value in sorted(_DOMAIN_TOKEN_TO_CAPABILITY_IDS.items())},
        "priority_prefix": _PRIORITY_PREFIX,
    }
)


def _normalize_priority(value: Any, *, default_priority: str) -> str:
    raw = str(value if value is not None else default_priority).strip().upper()
    return raw if raw in _PRIORITY_PREFIX else str(default_priority).strip().upper()


def _slug(value: str) -> str:
    out = "".join(ch if ("a" <= ch <= "z") or ("0" <= ch <= "9") else "_" for ch in str(value).strip().lower())
    out = out.strip("_")
    return out or "x"


def _stable_frontier_id(*, capability_id: str, explicit_frontier_id: Any = None) -> str:
    explicit = str(explicit_frontier_id if explicit_frontier_id is not None else "").strip()
    if explicit:
        return explicit
    return _slug(capability_id)


def _registry_known_capability_ids(registry: dict[str, Any]) -> set[str]:
    rows = registry.get("capabilities")
    if not isinstance(rows, list):
        return set()
    out: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        capability_id = str(row.get("capability_id", "")).strip()
        if capability_id:
            out.add(capability_id)
    return out


def _capabilities_from_tags(*, objective_tags: list[str], domain: str | None) -> set[str]:
    out: set[str] = set()
    for tag in sorted(set(objective_tags)):
        for capability_id in _MISSION_TAG_TO_CAPABILITY_IDS.get(tag, ()):
            out.add(capability_id)
    if domain:
        domain_slug = _slug(domain)
        for token, capability_ids in sorted(_DOMAIN_TOKEN_TO_CAPABILITY_IDS.items()):
            if token in domain_slug:
                out.update(capability_ids)
    return out


def _goal_rows(
    *,
    tick_u64: int,
    capability_ids: list[str],
    priority: str,
    max_goals_u64: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    prefix = _PRIORITY_PREFIX[str(priority)]
    limit = max(0, int(max_goals_u64))
    for idx, capability_id in enumerate(capability_ids):
        if idx >= limit:
            break
        goal_id = f"{prefix}{_slug(capability_id)}_{int(tick_u64):06d}_{int(idx):02d}"
        out.append(
            {
                "goal_id": goal_id,
                "capability_id": capability_id,
                "frontier_id": _stable_frontier_id(capability_id=capability_id),
                "status": "PENDING",
            }
        )
    return out


def _base_receipt(
    *,
    tick_u64: int,
    lane_name: str,
    status: str,
    reason_code: str,
    mission_present_b: bool,
    mission_hash: str | None,
    goals: list[dict[str, Any]],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_name": "mission_goal_ingest_receipt_v1",
        "schema_version": "v19_0",
        "receipt_id": "sha256:" + ("0" * 64),
        "tick_u64": int(tick_u64),
        "status": status,
        "reason_code": reason_code,
        "lane_name": str(lane_name),
        "mission_present_b": bool(mission_present_b),
        "mission_hash": mission_hash,
        "mapping_table_hash": _MAPPING_TABLE_HASH,
        "goal_count_u64": int(len(goals)),
        "goals": list(goals),
    }
    no_id = dict(payload)
    no_id.pop("receipt_id", None)
    payload["receipt_id"] = canon_hash_obj(no_id)
    validate_schema_v19(payload, "mission_goal_ingest_receipt_v1")
    return payload


def ingest_mission_goals(
    *,
    tick_u64: int,
    lane_name: str,
    mission_path: Path,
    lane_allowed_capability_ids: list[str],
    registry: dict[str, Any],
    default_priority: str,
    max_injected_goals_u64: int,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any] | None]:
    mission_present_b = mission_path.exists()
    lane_allowed = sorted({str(row).strip() for row in lane_allowed_capability_ids if str(row).strip()})
    registry_known = _registry_known_capability_ids(registry)

    if not mission_present_b:
        receipt = _base_receipt(
            tick_u64=tick_u64,
            lane_name=lane_name,
            status="MISSION_GOAL_SKIPPED",
            reason_code="MISSION_FILE_ABSENT",
            mission_present_b=False,
            mission_hash=None,
            goals=[],
        )
        return [], receipt, None

    if not mission_path.is_file():
        receipt = _base_receipt(
            tick_u64=tick_u64,
            lane_name=lane_name,
            status="MISSION_GOAL_REJECTED",
            reason_code="MISSION_PATH_INVALID",
            mission_present_b=True,
            mission_hash=None,
            goals=[],
        )
        return [], receipt, None

    try:
        raw_obj = json.loads(mission_path.read_text(encoding="utf-8"))
    except Exception:
        receipt = _base_receipt(
            tick_u64=tick_u64,
            lane_name=lane_name,
            status="MISSION_GOAL_REJECTED",
            reason_code="MISSION_PARSE_ERROR",
            mission_present_b=True,
            mission_hash=None,
            goals=[],
        )
        return [], receipt, None
    if not isinstance(raw_obj, dict):
        receipt = _base_receipt(
            tick_u64=tick_u64,
            lane_name=lane_name,
            status="MISSION_GOAL_REJECTED",
            reason_code="MISSION_SCHEMA_INVALID",
            mission_present_b=True,
            mission_hash=None,
            goals=[],
        )
        return [], receipt, None

    mission_payload = dict(raw_obj)
    try:
        validate_schema_v19(mission_payload, "mission_request_v1")
    except Exception:
        receipt = _base_receipt(
            tick_u64=tick_u64,
            lane_name=lane_name,
            status="MISSION_GOAL_REJECTED",
            reason_code="MISSION_SCHEMA_INVALID",
            mission_present_b=True,
            mission_hash=None,
            goals=[],
        )
        return [], receipt, None

    mission_hash = canon_hash_obj(mission_payload)
    enabled_b = bool(mission_payload.get("enabled_b", True))
    if not enabled_b:
        receipt = _base_receipt(
            tick_u64=tick_u64,
            lane_name=lane_name,
            status="MISSION_GOAL_SKIPPED",
            reason_code="MISSION_DISABLED",
            mission_present_b=True,
            mission_hash=mission_hash,
            goals=[],
        )
        return [], receipt, mission_payload

    objective_tags_raw = mission_payload.get("objective_tags")
    objective_tags: list[str] = []
    if isinstance(objective_tags_raw, list):
        objective_tags = sorted({_slug(row) for row in objective_tags_raw if str(row).strip()})
    domain = str(mission_payload.get("domain", "")).strip() or None

    mission_allowed_raw = mission_payload.get("allowed_capability_ids")
    mission_allowed: set[str] = set()
    if isinstance(mission_allowed_raw, list) and mission_allowed_raw:
        mission_allowed = {str(row).strip() for row in mission_allowed_raw if str(row).strip()}
    else:
        mission_allowed = _capabilities_from_tags(objective_tags=objective_tags, domain=domain)

    if not mission_allowed:
        receipt = _base_receipt(
            tick_u64=tick_u64,
            lane_name=lane_name,
            status="MISSION_GOAL_SKIPPED",
            reason_code="MISSION_NO_CAPABILITY_MATCH",
            mission_present_b=True,
            mission_hash=mission_hash,
            goals=[],
        )
        return [], receipt, mission_payload

    eligible = sorted(mission_allowed.intersection(set(lane_allowed)).intersection(registry_known))
    if not eligible:
        receipt = _base_receipt(
            tick_u64=tick_u64,
            lane_name=lane_name,
            status="MISSION_GOAL_SKIPPED",
            reason_code="MISSION_INTERSECTION_EMPTY",
            mission_present_b=True,
            mission_hash=mission_hash,
            goals=[],
        )
        return [], receipt, mission_payload

    priority = _normalize_priority(mission_payload.get("priority"), default_priority=default_priority)
    goals = _goal_rows(
        tick_u64=tick_u64,
        capability_ids=eligible,
        priority=priority,
        max_goals_u64=int(max_injected_goals_u64),
    )
    receipt = _base_receipt(
        tick_u64=tick_u64,
        lane_name=lane_name,
        status="MISSION_GOAL_ADDED",
        reason_code="MISSION_ACCEPTED",
        mission_present_b=True,
        mission_hash=mission_hash,
        goals=goals,
    )
    return goals, receipt, mission_payload


__all__ = ["ingest_mission_goals"]
