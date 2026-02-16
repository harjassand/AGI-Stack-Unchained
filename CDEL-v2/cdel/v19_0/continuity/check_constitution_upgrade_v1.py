"""Constitution kernel (CK) enforcement for constitution upgrades (L9)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common_v1 import fail, make_budget_tracker, validate_schema, verify_declared_id
from .loaders_v1 import ArtifactRef, load_artifact_ref


def _as_set_map(value: Any) -> dict[str, set[str]]:
    if not isinstance(value, dict):
        fail("CK_VERIFY_FAILURE", safe_halt=True)
    out: dict[str, set[str]] = {}
    for key, row in value.items():
        if not isinstance(row, list):
            fail("CK_VERIFY_FAILURE", safe_halt=True)
        out[str(key)] = {str(x) for x in row}
    return out


def _verify_monotone_strengthening(old_const: dict[str, Any], new_const: dict[str, Any]) -> None:
    old_types = {str(x) for x in old_const.get("admissible_upgrade_types", [])}
    new_types = {str(x) for x in new_const.get("admissible_upgrade_types", [])}
    if not old_types.issubset(new_types):
        fail("CK_VERIFY_FAILURE", safe_halt=True)

    old_map = _as_set_map(old_const.get("required_proof_map"))
    new_map = _as_set_map(new_const.get("required_proof_map"))
    for key, old_proofs in old_map.items():
        new_proofs = new_map.get(key)
        if new_proofs is None:
            fail("CK_VERIFY_FAILURE", safe_halt=True)
        if not old_proofs.issubset(new_proofs):
            fail("CK_VERIFY_FAILURE", safe_halt=True)


def _verify_conservative_extension(old_const: dict[str, Any], new_const: dict[str, Any]) -> None:
    old_map = _as_set_map(old_const.get("required_proof_map"))
    new_map = _as_set_map(new_const.get("required_proof_map"))
    for key, proofs in old_map.items():
        if key not in new_map or not proofs.issubset(new_map[key]):
            fail("CK_VERIFY_FAILURE", safe_halt=True)


def check_constitution_upgrade(
    *,
    store_root: Path,
    constitution_morphism_ref: ArtifactRef,
    budget: dict[str, Any],
) -> dict[str, Any]:
    tracker = make_budget_tracker(budget)

    morphism = load_artifact_ref(store_root, constitution_morphism_ref)
    tracker.consume_items(1)
    tracker.consume_steps(1)
    tracker.consume_bytes_read(morphism.canonical_size)

    morphism_payload = morphism.payload
    if not isinstance(morphism_payload, dict):
        fail("CK_VERIFY_FAILURE", safe_halt=True)

    validate_schema(morphism_payload, "constitution_morphism_v1")
    verify_declared_id(morphism_payload, "morphism_id")

    old_ref = morphism_payload.get("old_constitution_ref")
    new_ref = morphism_payload.get("new_constitution_ref")
    ck_ref = morphism_payload.get("ck_profile_ref")
    if not isinstance(old_ref, dict) or not isinstance(new_ref, dict) or not isinstance(ck_ref, dict):
        fail("CK_VERIFY_FAILURE", safe_halt=True)

    old_const = load_artifact_ref(store_root, old_ref)
    new_const = load_artifact_ref(store_root, new_ref)
    ck_profile = load_artifact_ref(store_root, ck_ref)
    tracker.consume_bytes_read(old_const.canonical_size + new_const.canonical_size + ck_profile.canonical_size)

    if not isinstance(old_const.payload, dict) or not isinstance(new_const.payload, dict) or not isinstance(ck_profile.payload, dict):
        fail("CK_VERIFY_FAILURE", safe_halt=True)

    validate_schema(old_const.payload, "continuity_constitution_v1")
    validate_schema(new_const.payload, "continuity_constitution_v1")
    validate_schema(ck_profile.payload, "constitution_kernel_profile_v1")
    verify_declared_id(old_const.payload, "constitution_id")
    verify_declared_id(new_const.payload, "constitution_id")
    verify_declared_id(ck_profile.payload, "ck_profile_id")

    checked_fields = ck_profile.payload.get("checked_fields")
    if not isinstance(checked_fields, list) or not checked_fields:
        fail("CK_VERIFY_FAILURE", safe_halt=True)

    for row in checked_fields:
        field = str(row)
        if field not in old_const.payload or field not in new_const.payload:
            fail("CK_VERIFY_FAILURE", safe_halt=True)

    change_class = str(morphism_payload.get("change_class", ""))
    if change_class == "MONOTONE_STRENGTHENING":
        _verify_monotone_strengthening(old_const.payload, new_const.payload)
    elif change_class == "CONSERVATIVE_EXTENSION":
        _verify_conservative_extension(old_const.payload, new_const.payload)
    else:
        fail("CK_VERIFY_FAILURE", safe_halt=True)

    if bool(morphism_payload.get("translator_totality_required", False)):
        if "NO_NEW_ACCEPT_PATH" not in {str(x) for x in morphism_payload.get("required_proofs", [])}:
            fail("CK_VERIFY_FAILURE", safe_halt=True)

    if bool(morphism_payload.get("constitutional_backrefute_required", False)):
        if "BACKREFUTE_LANE" not in {str(x) for x in morphism_payload.get("required_proofs", [])}:
            fail("CK_VERIFY_FAILURE", safe_halt=True)

    return {
        "morphism_id": str(morphism_payload.get("morphism_id")),
        "status": "PASS",
    }


__all__ = ["check_constitution_upgrade"]
