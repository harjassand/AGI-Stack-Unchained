"""Meta-law (C-CONT) enforcement for K/E/M upgrades."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common_v1 import fail, make_budget_tracker, validate_schema, verify_declared_id
from .loaders_v1 import ArtifactRef, load_artifact_ref


def _require_proofs_for_type(
    *,
    constitution_payload: dict[str, Any],
    morphism_payload: dict[str, Any],
) -> None:
    morphism_type = str(morphism_payload.get("morphism_type", "")).strip()
    required_map = constitution_payload.get("required_proof_map")
    if not isinstance(required_map, dict):
        fail("META_LAW_COMPLIANCE", safe_halt=True)

    required = required_map.get(morphism_type, [])
    if not isinstance(required, list):
        fail("META_LAW_COMPLIANCE", safe_halt=True)

    provided = morphism_payload.get("required_proofs")
    if not isinstance(provided, list):
        fail("META_LAW_COMPLIANCE", safe_halt=True)
    provided_set = {str(x) for x in provided}

    for row in required:
        if str(row) not in provided_set:
            fail("META_LAW_COMPLIANCE", safe_halt=True)


def _load_required_ref(*, store_root: Path, payload: dict[str, Any], key: str, reason: str) -> dict[str, Any]:
    ref = payload.get(key)
    if not isinstance(ref, dict):
        fail(reason, safe_halt=True)
    loaded = load_artifact_ref(store_root, ref)
    if not isinstance(loaded.payload, dict):
        fail(reason, safe_halt=True)
    return loaded.payload


def _enforce_m_pi_constraints(*, store_root: Path, morphism_payload: dict[str, Any]) -> None:
    mode = str(morphism_payload.get("representation_mode", "")).strip()
    if mode not in {"INJECTIVE", "LOSS_BOUNDED"}:
        fail("META_LAW_COMPLIANCE", safe_halt=True)

    decoder_refs = morphism_payload.get("decoder_artifact_refs")
    if not isinstance(decoder_refs, list) or not decoder_refs:
        fail("META_LAW_COMPLIANCE", safe_halt=True)
    for row in decoder_refs:
        if not isinstance(row, dict):
            fail("META_LAW_COMPLIANCE", safe_halt=True)
        _decoder = load_artifact_ref(store_root, row)

    collision_ref = morphism_payload.get("collision_suite_ref")
    if not isinstance(collision_ref, dict):
        fail("META_LAW_COMPLIANCE", safe_halt=True)
    _collision = load_artifact_ref(store_root, collision_ref)

    if mode == "LOSS_BOUNDED":
        loss_ref = morphism_payload.get("loss_bound_witness_ref")
        if not isinstance(loss_ref, dict):
            fail("META_LAW_COMPLIANCE", safe_halt=True)
        _loss = load_artifact_ref(store_root, loss_ref)

    if bool(morphism_payload.get("shared_nodes_multi_domain", False)):
        multiplex_ref = morphism_payload.get("multiplexing_proof_ref")
        if not isinstance(multiplex_ref, dict):
            fail("META_LAW_COMPLIANCE", safe_halt=True)
        _multiplex = load_artifact_ref(store_root, multiplex_ref)


def _enforce_m_d_constraints(*, store_root: Path, morphism_payload: dict[str, Any]) -> None:
    schedule_payload = _load_required_ref(
        store_root=store_root,
        payload=morphism_payload,
        key="udc_schedule_ref",
        reason="META_LAW_COMPLIANCE",
    )
    validate_schema(schedule_payload, "udc_schedule_v1")
    verify_declared_id(schedule_payload, "schedule_id")

    epsilon_udc = morphism_payload.get("epsilon_udc_u64")
    if not isinstance(epsilon_udc, int) or epsilon_udc < 0:
        fail("META_LAW_COMPLIANCE", safe_halt=True)


def _enforce_m_h_constraints(*, store_root: Path, morphism_payload: dict[str, Any]) -> None:
    cert_payload = _load_required_ref(
        store_root=store_root,
        payload=morphism_payload,
        key="constructor_conservativity_cert_ref",
        reason="META_LAW_COMPLIANCE",
    )
    validate_schema(cert_payload, "constructor_conservativity_cert_v1")
    verify_declared_id(cert_payload, "cert_id")
    if str(cert_payload.get("result", "")) != "PASS":
        fail("META_LAW_COMPLIANCE", safe_halt=True)


def _enforce_m_a_constraints(*, store_root: Path, morphism_payload: dict[str, Any]) -> None:
    cert_payload = _load_required_ref(
        store_root=store_root,
        payload=morphism_payload,
        key="meta_yield_cert_ref",
        reason="META_LAW_COMPLIANCE",
    )
    validate_schema(cert_payload, "meta_yield_cert_v1")
    verify_declared_id(cert_payload, "cert_id")

    horizon = int(cert_payload.get("horizon_u64", 0))
    series = cert_payload.get("y_series")
    if not isinstance(series, list) or not series:
        fail("META_LAW_COMPLIANCE", safe_halt=True)
    if horizon != len(series):
        fail("META_LAW_COMPLIANCE", safe_halt=True)
    prev: int | None = None
    for row in series:
        if not isinstance(row, int):
            fail("META_LAW_COMPLIANCE", safe_halt=True)
        if prev is not None and row < prev:
            fail("META_LAW_COMPLIANCE", safe_halt=True)
        prev = row


def _enforce_axis_specific_constraints(*, store_root: Path, morphism_payload: dict[str, Any]) -> None:
    morphism_type = str(morphism_payload.get("morphism_type", "")).strip()
    if morphism_type == "M_PI":
        _enforce_m_pi_constraints(store_root=store_root, morphism_payload=morphism_payload)
    elif morphism_type == "M_D":
        _enforce_m_d_constraints(store_root=store_root, morphism_payload=morphism_payload)
    elif morphism_type == "M_H":
        _enforce_m_h_constraints(store_root=store_root, morphism_payload=morphism_payload)
    elif morphism_type == "M_A":
        _enforce_m_a_constraints(store_root=store_root, morphism_payload=morphism_payload)


def enforce_meta_law_for_morphism(
    *,
    store_root: Path,
    continuity_constitution_ref: ArtifactRef,
    morphism_ref: ArtifactRef,
    budget: dict[str, Any],
) -> dict[str, Any]:
    tracker = make_budget_tracker(budget)

    constitution = load_artifact_ref(store_root, continuity_constitution_ref)
    morphism = load_artifact_ref(store_root, morphism_ref)
    tracker.consume_items(2)
    tracker.consume_steps(2)
    tracker.consume_bytes_read(constitution.canonical_size + morphism.canonical_size)

    constitution_payload = constitution.payload
    morphism_payload = morphism.payload
    if not isinstance(constitution_payload, dict) or not isinstance(morphism_payload, dict):
        fail("META_LAW_COMPLIANCE", safe_halt=True)

    validate_schema(constitution_payload, "continuity_constitution_v1")
    verify_declared_id(constitution_payload, "constitution_id")

    validate_schema(morphism_payload, "continuity_morphism_v1")
    verify_declared_id(morphism_payload, "morphism_id")

    admissible = constitution_payload.get("admissible_upgrade_types")
    if not isinstance(admissible, list):
        fail("META_LAW_COMPLIANCE", safe_halt=True)
    if str(morphism_payload.get("morphism_type", "")) not in {str(x) for x in admissible}:
        fail("META_LAW_COMPLIANCE", safe_halt=True)

    _require_proofs_for_type(constitution_payload=constitution_payload, morphism_payload=morphism_payload)
    _enforce_axis_specific_constraints(store_root=store_root, morphism_payload=morphism_payload)

    return {
        "constitution_id": str(constitution_payload.get("constitution_id")),
        "morphism_id": str(morphism_payload.get("morphism_id")),
        "status": "PASS",
    }


def check_meta_law(
    *,
    store_root: Path,
    meta_law_morphism_ref: ArtifactRef,
    budget: dict[str, Any],
) -> dict[str, Any]:
    tracker = make_budget_tracker(budget)
    meta_morphism = load_artifact_ref(store_root, meta_law_morphism_ref)
    tracker.consume_items(1)
    tracker.consume_steps(1)
    tracker.consume_bytes_read(meta_morphism.canonical_size)

    payload = meta_morphism.payload
    if not isinstance(payload, dict):
        fail("META_LAW_COMPLIANCE", safe_halt=True)

    validate_schema(payload, "meta_law_morphism_v1")
    verify_declared_id(payload, "morphism_id")

    constitution_ref = payload.get("continuity_constitution_ref")
    target_morphism_ref = payload.get("target_morphism_ref")
    if not isinstance(constitution_ref, dict) or not isinstance(target_morphism_ref, dict):
        fail("META_LAW_COMPLIANCE", safe_halt=True)

    enforcement = enforce_meta_law_for_morphism(
        store_root=store_root,
        continuity_constitution_ref=constitution_ref,
        morphism_ref=target_morphism_ref,
        budget=budget,
    )
    return {
        "meta_law_morphism_id": str(payload.get("morphism_id")),
        "enforcement": enforcement,
    }


__all__ = ["check_meta_law", "enforce_meta_law_for_morphism"]
