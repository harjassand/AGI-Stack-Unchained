#!/usr/bin/env python3
"""Deterministic governance preflight for v19 long disciplined runs."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "CDEL-v2") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "CDEL-v2"))

from cdel.v1_7r.canon import canon_bytes
from cdel.v18_0.omega_common_v1 import canon_hash_obj, load_canon_dict
from cdel.v19_0.common_v1 import validate_schema as validate_schema_v19


DEFAULT_PACK = "campaigns/rsi_omega_daemon_v19_0_long_run_v1/rsi_omega_daemon_pack_v1.json"
DEFAULT_RUN_ROOT = "runs/long_run_preflight_v1"
DEFAULT_SUMMARY = "LONG_RUN_PREFLIGHT_SUMMARY_v1.json"

REQUIRED_SCHEMA_NAMES = (
    "long_run_preflight_summary_v1",
    "dependency_debt_state_v1",
    "dependency_routing_receipt_v1",
    "utility_policy_v1",
    "utility_proof_receipt_v1",
    "anti_monopoly_state_v1",
)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canon_bytes(payload) + b"\n")


def _run_git(args: list[str]) -> str:
    proc = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return ""
    return str(proc.stdout or "").strip()


def _dirty_tree_b() -> bool:
    status = _run_git(["status", "--porcelain"])
    return bool(status.splitlines())


def _head_commit() -> str:
    head = _run_git(["rev-parse", "HEAD"])
    return head or "UNKNOWN"


def _branch_name() -> str:
    branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    return branch or "UNKNOWN"


def _head_commit_created_at_utc() -> str:
    value = _run_git(["show", "-s", "--format=%cI", "HEAD"])
    if value:
        return str(value).replace("+00:00", "Z")
    return "1970-01-01T00:00:00Z"


def _schema_required_fields_ok(schema_path: Path, required_fields: set[str]) -> bool:
    if not schema_path.exists() or not schema_path.is_file():
        return False
    payload = json.loads(schema_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return False
    required = payload.get("required")
    if not isinstance(required, list):
        return False
    required_set = {str(row) for row in required}
    return required_fields.issubset(required_set)


def _schema_has_property_keys(schema_path: Path, keys: set[str]) -> bool:
    if not schema_path.exists() or not schema_path.is_file():
        return False
    payload = json.loads(schema_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return False
    props = payload.get("properties")
    if not isinstance(props, dict):
        return False
    return keys.issubset({str(row) for row in props.keys()})


def _schema_property_const(schema_path: Path, *, property_name: str) -> str | None:
    if not schema_path.exists() or not schema_path.is_file():
        return None
    payload = json.loads(schema_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    props = payload.get("properties")
    if not isinstance(props, dict):
        return None
    row = props.get(str(property_name))
    if not isinstance(row, dict):
        return None
    const = row.get("const")
    if not isinstance(const, str) or not const.strip():
        return None
    return str(const).strip()


def _summary_id(payload: dict[str, Any]) -> str:
    no_id = dict(payload)
    no_id.pop("id", None)
    return canon_hash_obj(no_id)


def _require_summary_shape(payload: dict[str, Any]) -> None:
    required_top = {"schema_id", "id", "created_at_utc", "git", "env", "schema_checks", "governance_checks"}
    if not required_top.issubset(set(payload.keys())):
        raise RuntimeError("SCHEMA_FAIL:LONG_RUN_PREFLIGHT_SUMMARY_MISSING_FIELD")


def main() -> None:
    ap = argparse.ArgumentParser(prog="preflight_long_run_v1")
    ap.add_argument("--campaign_pack", default=DEFAULT_PACK)
    ap.add_argument("--run_root", default=DEFAULT_RUN_ROOT)
    ap.add_argument("--summary_path", default=DEFAULT_SUMMARY)
    args = ap.parse_args()

    campaign_pack = (REPO_ROOT / str(args.campaign_pack)).resolve()
    summary_path = (REPO_ROOT / str(args.summary_path)).resolve()

    if not campaign_pack.exists() or not campaign_pack.is_file():
        raise SystemExit(f"missing pack: {campaign_pack}")

    pack_payload = load_canon_dict(campaign_pack)
    long_run_profile_rel = str(pack_payload.get("long_run_profile_rel", "")).strip()
    if not long_run_profile_rel:
        raise SystemExit("SCHEMA_FAIL:PACK_MISSING_LONG_RUN_PROFILE")
    profile_path = (campaign_pack.parent / long_run_profile_rel).resolve()
    if not profile_path.exists() or not profile_path.is_file():
        raise SystemExit("MISSING_STATE_INPUT:LONG_RUN_PROFILE")
    profile_payload = load_canon_dict(profile_path)
    validate_schema_v19(profile_payload, "long_run_profile_v1")

    dirty_tree_allowed_b = str(os.environ.get("OMEGA_CCAP_ALLOW_DIRTY_TREE", "0")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    dirty_tree_b = _dirty_tree_b()

    missing_schemas: list[str] = []
    mirror_mismatches: list[str] = []
    genesis_schema_dir = REPO_ROOT / "Genesis" / "schema" / "v19_0"
    cdel_mirror_dir = REPO_ROOT / "CDEL-v2" / "Genesis" / "schema" / "v19_0"

    for schema_name in REQUIRED_SCHEMA_NAMES:
        genesis_path = genesis_schema_dir / f"{schema_name}.jsonschema"
        mirror_path = cdel_mirror_dir / f"{schema_name}.jsonschema"
        if not genesis_path.exists() or not genesis_path.is_file():
            missing_schemas.append(f"Genesis/schema/v19_0/{schema_name}.jsonschema")
            continue
        if not mirror_path.exists() or not mirror_path.is_file():
            missing_schemas.append(f"CDEL-v2/Genesis/schema/v19_0/{schema_name}.jsonschema")
            continue
        if genesis_path.read_bytes() != mirror_path.read_bytes():
            mirror_mismatches.append(schema_name)

    utility_policy_rel = str(profile_payload.get("utility_policy_rel", "")).strip()
    utility_policy_id = str(profile_payload.get("utility_policy_id", "")).strip()
    utility_policy_path = (campaign_pack.parent / utility_policy_rel).resolve() if utility_policy_rel else None
    utility_policy_ok_b = False
    if utility_policy_rel and utility_policy_id and isinstance(utility_policy_path, Path):
        rel_path = Path(utility_policy_rel)
        rel_safe_b = not rel_path.is_absolute() and ".." not in rel_path.parts
        if rel_safe_b and utility_policy_path.exists() and utility_policy_path.is_file():
            try:
                utility_policy_payload = load_canon_dict(utility_policy_path)
                validate_schema_v19(utility_policy_payload, "utility_policy_v1")
                declared_policy_id = str(utility_policy_payload.get("policy_id", "")).strip()
                utility_policy_no_id = dict(utility_policy_payload)
                utility_policy_no_id.pop("policy_id", None)
                policy_hash = canon_hash_obj(utility_policy_no_id)
                utility_policy_ok_b = bool(
                    declared_policy_id
                    and declared_policy_id == policy_hash
                    and declared_policy_id == utility_policy_id
                )
            except Exception:
                utility_policy_ok_b = False
    pack_profile_id = str(pack_payload.get("long_run_profile_id", "")).strip()
    profile_id = str(profile_payload.get("profile_id", "")).strip()
    profile_no_id = dict(profile_payload)
    profile_no_id.pop("profile_id", None)
    profile_hash = canon_hash_obj(profile_no_id)
    profile_pin_ok_b = bool(pack_profile_id and profile_id and pack_profile_id == profile_id and profile_id == profile_hash)

    debt_schema_path = genesis_schema_dir / "dependency_debt_state_v1.jsonschema"
    anti_schema_path = genesis_schema_dir / "anti_monopoly_state_v1.jsonschema"
    routing_schema_path = genesis_schema_dir / "dependency_routing_receipt_v1.jsonschema"
    utility_receipt_schema_path = genesis_schema_dir / "utility_proof_receipt_v1.jsonschema"

    debt_state_schema_base_ok_b = _schema_required_fields_ok(
        debt_schema_path,
        {
            "schema_id",
            "id",
            "tick_u64",
            "debt_counters_by_key",
            "hard_lock_active_b",
            "hard_lock_keys",
            "ticks_without_frontier_attempt_by_key",
            "pending_frontier_goal_ids",
            "last_frontier_attempt_tick_by_key",
            "failed_patch_ban_by_patch_hash",
            "failed_nontriviality_shape_ban_by_shape_hash",
            "updated_at_utc",
        },
    )
    dependency_schema_versions_pinned_b = bool(
        isinstance(profile_payload.get("dependency_debt"), dict)
        and profile_pin_ok_b
        and _schema_property_const(debt_schema_path, property_name="schema_version") == "v19_0"
        and _schema_property_const(routing_schema_path, property_name="schema_version") == "v19_0"
    )
    debt_state_schema_ok_b = bool(debt_state_schema_base_ok_b and dependency_schema_versions_pinned_b)

    anti_monopoly_schema_ok_b = _schema_required_fields_ok(
        anti_schema_path,
        {
            "schema_id",
            "id",
            "tick_u64",
            "window_u64",
            "max_share_q32",
            "counts_by_lane_id",
            "counts_by_campaign_id",
            "last_selected_lane_id",
            "last_selected_campaign_id",
            "updated_at_utc",
        },
    )

    hard_lock_unlock_contract_ok_b = (
        _schema_has_property_keys(
            routing_schema_path,
            {
                "hard_lock_active_b",
                "hard_lock_keys",
                "forced_heavy_b",
                "forced_heavy_reason_code",
                "forced_heavy_target_debt_keys",
            },
        )
        and _schema_has_property_keys(
            utility_receipt_schema_path,
            {
                "utility_class",
                "targeted_debt_keys",
                "debt_delta_by_key",
                "reduced_specific_trigger_keys_b",
            },
        )
    )

    anti_monopoly_used_b = isinstance(profile_payload.get("anti_monopoly"), dict)

    created_at_utc = _head_commit_created_at_utc()
    summary: dict[str, Any] = {
        "schema_id": "long_run_preflight_summary_v1",
        "id": "sha256:" + ("0" * 64),
        "created_at_utc": str(created_at_utc),
        "git": {
            "head_commit": _head_commit(),
            "branch": _branch_name(),
            "dirty_tree_b": bool(dirty_tree_b),
            "dirty_tree_allowed_b": bool(dirty_tree_allowed_b),
        },
        "env": {
            "OMEGA_META_CORE_ACTIVATION_MODE": str(os.environ.get("OMEGA_META_CORE_ACTIVATION_MODE", "simulate") or "simulate"),
            "OMEGA_V19_DETERMINISTIC_TIMING": str(os.environ.get("OMEGA_V19_DETERMINISTIC_TIMING", "0") or "0"),
            "ORCH_LLM_BACKEND": str(os.environ.get("ORCH_LLM_BACKEND", "mlx") or "mlx"),
        },
        "schema_checks": {
            "missing_schemas": [str(row) for row in sorted(set(missing_schemas))],
            "mirror_mismatches": [str(row) for row in sorted(set(mirror_mismatches))],
        },
        "governance_checks": {
            "utility_policy_ok_b": bool(utility_policy_ok_b),
            "debt_state_schema_ok_b": bool(debt_state_schema_ok_b),
            "anti_monopoly_schema_ok_b": bool(anti_monopoly_schema_ok_b and anti_monopoly_used_b),
            "hard_lock_unlock_contract_ok_b": bool(hard_lock_unlock_contract_ok_b),
        },
    }

    summary["id"] = _summary_id(summary)
    validate_schema_v19(summary, "long_run_preflight_summary_v1")
    _require_summary_shape(summary)
    _write_json(summary_path, summary)

    pass_b = (
        ((not dirty_tree_b) or dirty_tree_allowed_b)
        and not summary["schema_checks"]["missing_schemas"]
        and not summary["schema_checks"]["mirror_mismatches"]
        and all(bool(value) for value in summary["governance_checks"].values())
    )
    print(str(summary_path))
    print("PASS" if pass_b else "FAIL")
    raise SystemExit(0 if pass_b else 1)


if __name__ == "__main__":
    main()
