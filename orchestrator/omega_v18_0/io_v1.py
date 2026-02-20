"""I/O helpers for omega daemon v18.0."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cdel.v18_0.omega_common_v1 import (
    canon_hash_obj,
    ensure_sha256,
    fail,
    load_canon_dict,
    require_relpath,
    validate_schema,
)
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
_OPTIONAL_FILES = [
    "omega_bid_market_config_v1.json",
]
_PACK_SCHEMAS = {"rsi_omega_daemon_pack_v1", "rsi_omega_daemon_pack_v2"}
_PACK_V2_REQUIRED_PINNED = [
    ("coordinator_isa_program_rel", "coordinator_isa_program_id", "program_id"),
    ("coordinator_opcode_table_rel", "coordinator_opcode_table_id", "opcode_table_id"),
]
_PACK_V2_OPTIONAL_PINNED = [
    ("predictor_weights_rel", "predictor_id", "predictor_id"),
    ("objective_j_profile_rel", "objective_j_profile_id", "profile_id"),
    ("policy_budget_spec_rel", "policy_budget_spec_id", None),
    ("policy_determinism_contract_rel", "policy_determinism_contract_id", "determinism_contract_id"),
    ("policy_merge_policy_rel", "policy_merge_policy_id", "merge_policy_id"),
    ("policy_selection_policy_rel", "policy_selection_policy_id", "selection_policy_id"),
    ("policy_vm_air_profile_rel", "policy_vm_air_profile_id", "air_profile_id"),
    (
        "policy_vm_winterfell_backend_contract_rel",
        "policy_vm_winterfell_backend_contract_id",
        "backend_contract_id",
    ),
    ("policy_vm_action_kind_enum_rel", "policy_vm_action_kind_enum_id", "action_kind_enum_id"),
    (
        "policy_vm_candidate_campaign_ids_list_rel",
        "policy_vm_candidate_campaign_ids_list_id",
        "candidate_campaign_ids_list_id",
    ),
]
_PACK_V2_OPTIONAL_COPY_ONLY = [
    "shadow_regime_proposal_rel",
    "shadow_evaluation_tiers_rel",
    "shadow_protected_roots_profile_rel",
    "shadow_corpus_descriptor_rel",
    "shadow_witnessed_determinism_profile_rel",
    "shadow_j_comparison_profile_rel",
    "shadow_handoff_receipt_rel",
    "shadow_observed_writes_rel",
]
_GOAL_QUEUE_BASE_PATH_REL = Path("goals") / "omega_goal_queue_v1.json"
_GOAL_QUEUE_EFFECTIVE_PATH_REL = Path("goals") / "omega_goal_queue_effective_v1.json"


def _copy_required_json(*, source_root: Path, config_dir: Path, rel: str) -> None:
    src = source_root / rel
    if not src.exists() or not src.is_file():
        fail("MISSING_STATE_INPUT")
    payload = load_canon_dict(src)
    write_canon_json(config_dir / rel, payload)


def _copy_pinned_json_from_pack(
    *,
    source_root: Path,
    config_dir: Path,
    pack: dict[str, Any],
    rel_key: str,
    id_key: str,
    payload_id_field: str | None = None,
    optional: bool = False,
) -> str | None:
    rel_raw = str(pack.get(rel_key, "")).strip()
    id_raw = str(pack.get(id_key, "")).strip()
    if optional and not rel_raw and not id_raw:
        return None
    if bool(rel_raw) != bool(id_raw):
        fail("SCHEMA_FAIL")
    rel = require_relpath(rel_raw)
    declared_id = ensure_sha256(id_raw, reason="PIN_HASH_MISMATCH")
    src = source_root / rel
    if not src.exists() or not src.is_file():
        fail("MISSING_STATE_INPUT")
    payload = load_canon_dict(src)
    observed_id = None
    if payload_id_field:
        observed_id_raw = payload.get(payload_id_field)
        if isinstance(observed_id_raw, str) and observed_id_raw.strip():
            observed_id = ensure_sha256(observed_id_raw, reason="PIN_HASH_MISMATCH")
            payload_no_id = dict(payload)
            payload_no_id.pop(payload_id_field, None)
            if canon_hash_obj(payload_no_id) != observed_id:
                fail("PIN_HASH_MISMATCH")
    if observed_id is None:
        observed_id = canon_hash_obj(payload)
    if observed_id != declared_id:
        fail("PIN_HASH_MISMATCH")
    write_canon_json(config_dir / rel, payload)
    return observed_id


def _copy_policy_programs_from_pack(
    *,
    source_root: Path,
    config_dir: Path,
    pack: dict[str, Any],
) -> list[str]:
    rows = pack.get("policy_programs")
    if not isinstance(rows, list) or not rows:
        fail("SCHEMA_FAIL")
    if len(rows) > 100:
        fail("SCHEMA_FAIL")
    out: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        rel_raw = str(row.get("program_rel", "")).strip()
        id_raw = str(row.get("program_id", "")).strip()
        if not rel_raw or not id_raw:
            fail("SCHEMA_FAIL")
        rel = require_relpath(rel_raw)
        declared_id = ensure_sha256(id_raw, reason="PIN_HASH_MISMATCH")
        src = source_root / rel
        if not src.exists() or not src.is_file():
            fail("MISSING_STATE_INPUT")
        payload = load_canon_dict(src)
        observed = payload.get("program_id")
        if isinstance(observed, str) and observed.strip():
            observed_id = ensure_sha256(observed, reason="PIN_HASH_MISMATCH")
            payload_no_id = dict(payload)
            payload_no_id.pop("program_id", None)
            if canon_hash_obj(payload_no_id) != observed_id:
                fail("PIN_HASH_MISMATCH")
        else:
            observed_id = canon_hash_obj(payload)
        if observed_id != declared_id:
            fail("PIN_HASH_MISMATCH")
        write_canon_json(config_dir / rel, payload)
        out.append(observed_id)
    return out


def _copy_optional_relfile_from_pack(
    *,
    source_root: Path,
    config_dir: Path,
    pack: dict[str, Any],
    rel_key: str,
) -> None:
    rel_raw = str(pack.get(rel_key, "")).strip()
    if not rel_raw:
        return
    rel = require_relpath(rel_raw)
    src = source_root / rel
    if not src.exists() or not src.is_file():
        fail("MISSING_STATE_INPUT")
    payload = load_canon_dict(src)
    write_canon_json(config_dir / rel, payload)


def freeze_pack_config(*, campaign_pack: Path, config_dir: Path) -> tuple[dict[str, Any], str]:
    pack = load_canon_dict(campaign_pack)
    pack_schema = str(pack.get("schema_version", "")).strip()
    if pack_schema not in _PACK_SCHEMAS:
        fail("SCHEMA_FAIL")
    validate_schema(pack, pack_schema)

    source_root = campaign_pack.parent
    for rel in _REQUIRED_FILES:
        _copy_required_json(source_root=source_root, config_dir=config_dir, rel=rel)

    for rel in _OPTIONAL_FILES:
        src = source_root / rel
        if not src.exists():
            continue
        if not src.is_file():
            fail("SCHEMA_FAIL")
        payload = load_canon_dict(src)
        # Optional files are still schema-validated when present to keep
        # downstream hashing deterministic and fail-closed.
        schema_version = str(payload.get("schema_version", "")).strip()
        if schema_version:
            validate_schema(payload, schema_version)
        write_canon_json(config_dir / rel, payload)

    if pack_schema == "rsi_omega_daemon_pack_v2":
        for rel_key, id_key, payload_id_field in _PACK_V2_REQUIRED_PINNED:
            _copy_pinned_json_from_pack(
                source_root=source_root,
                config_dir=config_dir,
                pack=pack,
                rel_key=rel_key,
                id_key=id_key,
                payload_id_field=payload_id_field,
                optional=False,
            )
        for rel_key, id_key, payload_id_field in _PACK_V2_OPTIONAL_PINNED:
            _copy_pinned_json_from_pack(
                source_root=source_root,
                config_dir=config_dir,
                pack=pack,
                rel_key=rel_key,
                id_key=id_key,
                payload_id_field=payload_id_field,
                optional=True,
            )
        policy_mode = str(pack.get("policy_vm_mode", "DECISION_ONLY")).strip().upper()
        if policy_mode in {"PROPOSAL_ONLY", "DUAL"}:
            _copy_policy_programs_from_pack(
                source_root=source_root,
                config_dir=config_dir,
                pack=pack,
            )
        elif isinstance(pack.get("policy_programs"), list):
            _copy_policy_programs_from_pack(
                source_root=source_root,
                config_dir=config_dir,
                pack=pack,
            )
        for rel_key in _PACK_V2_OPTIONAL_COPY_ONLY:
            _copy_optional_relfile_from_pack(
                source_root=source_root,
                config_dir=config_dir,
                pack=pack,
                rel_key=rel_key,
            )

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
