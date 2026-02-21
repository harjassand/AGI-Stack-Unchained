"""Replay verification for epistemic reducer artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ..common_v1 import canon_hash_obj, ensure_sha256, fail, validate_schema, verify_object_id
from .reduce_v1 import reduce_mobs_to_qxwmr_graph_with_strip, verify_mob_payload
from .type_registry_v1 import (
    build_type_binding,
    is_legacy_registry,
    validate_registry_transition,
    validate_type_registry,
)


def _load_single(dir_path: Path, suffix: str) -> dict[str, Any]:
    rows = sorted(dir_path.glob(f"sha256_*.{suffix}"), key=lambda p: p.as_posix())
    if len(rows) != 1:
        fail("MISSING_STATE_INPUT")
    import json

    payload = json.loads(rows[0].read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        fail("SCHEMA_FAIL")
    if canon_hash_obj(payload) != "sha256:" + rows[0].name.split(".", 1)[0].split("_", 1)[1]:
        fail("NONDETERMINISTIC")
    return payload


def _load_optional_single(dir_path: Path, suffix: str) -> dict[str, Any] | None:
    rows = sorted(dir_path.glob(f"sha256_*.{suffix}"), key=lambda p: p.as_posix())
    if not rows:
        return None
    if len(rows) != 1:
        fail("MISSING_STATE_INPUT")
    payload = json.loads(rows[0].read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        fail("SCHEMA_FAIL")
    if canon_hash_obj(payload) != "sha256:" + rows[0].name.split(".", 1)[0].split("_", 1)[1]:
        fail("NONDETERMINISTIC")
    return payload


def _mob_payload_hash(payload: dict[str, Any]) -> str:
    try:
        text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except Exception:  # noqa: BLE001
        fail("SCHEMA_FAIL")
        return "sha256:" + ("0" * 64)
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_rows(dir_path: Path, suffix: str, *, schema_name: str, id_field: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(dir_path.glob(f"sha256_*.{suffix}"), key=lambda p: p.as_posix()):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            fail("SCHEMA_FAIL")
        if canon_hash_obj(payload) != "sha256:" + path.name.split(".", 1)[0].split("_", 1)[1]:
            fail("NONDETERMINISTIC")
        validate_schema(payload, schema_name)
        verify_object_id(payload, id_field=id_field)
        rows.append(payload)
    return rows


def verify_reduce(state_root: Path) -> dict[str, Any]:
    replay_root = state_root / "epistemic" / "replay_inputs"
    if not replay_root.exists() or not replay_root.is_dir():
        fail("MISSING_STATE_INPUT")

    episode_manifest = _load_single(replay_root / "episode", "epistemic_episode_outbox_v1.json")
    pinset = _load_single(replay_root / "episode", "epistemic_pinset_v1.json")
    _ = _load_single(replay_root / "episode", "epistemic_episode_complete_marker_v1.json")
    reduce_contract = _load_single(replay_root / "contracts", "epistemic_reduce_contract_v1.json")
    instruction_strip_contract = _load_single(replay_root / "contracts", "epistemic_instruction_strip_contract_v1.json")
    calibration = _load_single(replay_root / "contracts", "epistemic_confidence_calibration_v1.json")
    type_registry_payload = _load_optional_single(replay_root / "contracts", "epistemic_type_registry_v1.json")
    parent_type_registry_payload = _load_optional_single(replay_root / "contracts", "epistemic_type_registry_parent_v1.json")
    type_registry_id: str | None = None
    legacy_registry_b = False
    if type_registry_payload is not None:
        type_registry_payload = validate_type_registry(type_registry_payload)
        type_registry_id = ensure_sha256(type_registry_payload.get("registry_id"), reason="SCHEMA_FAIL")
        legacy_registry_b = is_legacy_registry(type_registry_payload)
        if parent_type_registry_payload is not None:
            parent_type_registry_payload = validate_type_registry(parent_type_registry_payload)
            transition = validate_registry_transition(
                parent=parent_type_registry_payload,
                child=type_registry_payload,
            )
            legacy_registry_b = bool(transition.get("legacy_registry_b", legacy_registry_b))
    accepted_versions_payload = _load_optional_single(replay_root / "contracts", "accepted_mob_schema_versions_v1.json")
    if accepted_versions_payload is None:
        accepted_versions = ["epistemic_model_output_v1"]
    else:
        if str(accepted_versions_payload.get("schema_version", "")) != "accepted_mob_schema_versions_v1":
            fail("SCHEMA_FAIL")
        rows = accepted_versions_payload.get("accepted_mob_schema_versions")
        if not isinstance(rows, list):
            fail("SCHEMA_FAIL")
        accepted_versions = [str(row).strip() for row in rows if str(row).strip()]
        if not accepted_versions:
            fail("SCHEMA_FAIL")

    mob_paths = sorted(
        list((replay_root / "mobs").glob("sha256_*.epistemic_model_output_v1.json"))
        + list((replay_root / "mobs").glob("sha256_*.epistemic_model_output_v2.json")),
        key=lambda p: p.as_posix(),
    )
    if not mob_paths:
        fail("MISSING_STATE_INPUT")
    mobs: list[dict[str, Any]] = []
    for path in mob_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            fail("SCHEMA_FAIL")
        schema_version = str(payload.get("schema_version", "")).strip()
        expected_hash = "sha256:" + path.name.split(".", 1)[0].split("_", 1)[1]
        if schema_version == "epistemic_model_output_v1":
            observed_hash = _mob_payload_hash(payload)
        elif schema_version == "epistemic_model_output_v2":
            observed_hash = canon_hash_obj(payload)
        else:
            fail("SCHEMA_FAIL")
            observed_hash = ""
        if observed_hash != expected_hash:
            fail("NONDETERMINISTIC")
        verify_mob_payload(payload)
        mobs.append(payload)

    mob_receipts_by_id: dict[str, dict[str, Any]] = {}
    receipt_paths = sorted((replay_root / "mob_receipts").glob("sha256_*.epistemic_mob_receipt_v1.json"), key=lambda p: p.as_posix())
    for path in receipt_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            fail("SCHEMA_FAIL")
        if canon_hash_obj(payload) != "sha256:" + path.name.split(".", 1)[0].split("_", 1)[1]:
            fail("NONDETERMINISTIC")
        validate_schema(payload, "epistemic_mob_receipt_v1")
        receipt_id = verify_object_id(payload, id_field="mob_receipt_id")
        mob_receipts_by_id[receipt_id] = payload

    mob_blob_bytes_by_id: dict[str, bytes] = {}
    blob_dir = replay_root / "mob_blobs" / "sha256"
    if blob_dir.exists() and blob_dir.is_dir():
        for path in sorted(blob_dir.glob("*"), key=lambda p: p.as_posix()):
            if not path.is_file():
                continue
            digest = path.name.strip()
            if len(digest) != 64:
                fail("SCHEMA_FAIL")
            blob = path.read_bytes()
            mob_blob_id = f"sha256:{digest}"
            if "sha256:" + hashlib.sha256(blob).hexdigest() != mob_blob_id:
                fail("HASH_MISMATCH")
            mob_blob_bytes_by_id[mob_blob_id] = blob

    episode_id = str(episode_manifest.get("episode_id", "")).strip()
    if not episode_id:
        fail("SCHEMA_FAIL")

    recomputed_result = reduce_mobs_to_qxwmr_graph_with_strip(
        episode_id=episode_id,
        mob_payloads=mobs,
        reduce_contract=reduce_contract,
        instruction_strip_contract=instruction_strip_contract,
        calibration=calibration,
        accepted_mob_schema_versions=accepted_versions,
        mob_blob_bytes_by_id=mob_blob_bytes_by_id,
        mob_receipts_by_id=mob_receipts_by_id,
        type_registry_id=type_registry_id,
    )
    recomputed = dict(recomputed_result.get("graph") or {})
    recomputed_strip_receipts = [
        dict(row)
        for row in list(recomputed_result.get("strip_receipts") or [])
        if isinstance(row, dict)
    ]

    graph_dir = state_root / "epistemic" / "graphs"
    observed = _load_single(graph_dir, "qxwmr_graph_v1.json")
    if canon_hash_obj(recomputed) != canon_hash_obj(observed):
        fail("REDUCE_REPLAY_MISMATCH")
    observed_strip_receipts = _load_rows(
        state_root / "epistemic" / "strip_receipts",
        "epistemic_instruction_strip_receipt_v1.json",
        schema_name="epistemic_instruction_strip_receipt_v1",
        id_field="receipt_id",
    )
    replay_strip_receipts = _load_rows(
        replay_root / "strip_receipts",
        "epistemic_instruction_strip_receipt_v1.json",
        schema_name="epistemic_instruction_strip_receipt_v1",
        id_field="receipt_id",
    )
    if not observed_strip_receipts or not replay_strip_receipts:
        fail("MISSING_STATE_INPUT")
    observed_by_id = {
        ensure_sha256(row.get("receipt_id"), reason="SCHEMA_FAIL"): row for row in observed_strip_receipts
    }
    replay_by_id = {
        ensure_sha256(row.get("receipt_id"), reason="SCHEMA_FAIL"): row for row in replay_strip_receipts
    }
    recomputed_by_id = {
        ensure_sha256(row.get("receipt_id"), reason="SCHEMA_FAIL"): row for row in recomputed_strip_receipts
    }
    if set(observed_by_id.keys()) != set(recomputed_by_id.keys()):
        fail("NONDETERMINISTIC")
    if set(replay_by_id.keys()) != set(recomputed_by_id.keys()):
        fail("NONDETERMINISTIC")
    for receipt_id in sorted(recomputed_by_id.keys()):
        if canon_hash_obj(observed_by_id[receipt_id]) != canon_hash_obj(recomputed_by_id[receipt_id]):
            fail("NONDETERMINISTIC")
        if canon_hash_obj(replay_by_id[receipt_id]) != canon_hash_obj(recomputed_by_id[receipt_id]):
            fail("NONDETERMINISTIC")

    observed_type_binding_paths = sorted(
        (state_root / "epistemic" / "type_bindings").glob("sha256_*.epistemic_type_binding_v1.json"),
        key=lambda p: p.as_posix(),
    )
    if type_registry_payload is None:
        if observed_type_binding_paths:
            fail("NONDETERMINISTIC")
    else:
        if len(observed_type_binding_paths) != 1:
            fail("MISSING_STATE_INPUT")
        observed_type_binding = _load_single(state_root / "epistemic" / "type_bindings", "epistemic_type_binding_v1.json")
        validate_schema(observed_type_binding, "epistemic_type_binding_v1")
        verify_object_id(observed_type_binding, id_field="binding_id")
        provisionals = _load_rows(
            replay_root / "type" / "provisionals",
            "epistemic_type_provisional_v1.json",
            schema_name="epistemic_type_provisional_v1",
            id_field="provisional_id",
        )
        ratifications = _load_rows(
            replay_root / "type" / "ratifications",
            "epistemic_type_ratification_receipt_v1.json",
            schema_name="epistemic_type_ratification_receipt_v1",
            id_field="receipt_id",
        )
        recomputed_binding = build_type_binding(
            graph=recomputed,
            type_registry=type_registry_payload,
            provisionals=provisionals,
            ratifications=ratifications,
        )
        if canon_hash_obj(recomputed_binding) != canon_hash_obj(observed_type_binding):
            fail("NONDETERMINISTIC")
        if str(recomputed_binding.get("outcome", "")) != "ACCEPT":
            fail("TYPE_GOVERNANCE_FAIL")
        graph_type_registry_id = observed.get("type_registry_id")
        if graph_type_registry_id is not None and ensure_sha256(graph_type_registry_id, reason="SCHEMA_FAIL") != type_registry_id:
            fail("NONDETERMINISTIC")

    pinset_id_manifest = str(episode_manifest.get("pinset_id", "")).strip()
    pinset_id = verify_object_id(pinset, id_field="pinset_id")
    if pinset_id_manifest != pinset_id:
        fail("NONDETERMINISTIC")

    return {
        "status": "VALID",
        "graph_id": str(observed.get("graph_id", "")),
        "strip_receipt_id": ensure_sha256(recomputed_result.get("strip_receipt_id"), reason="SCHEMA_FAIL"),
        "legacy_registry_b": bool(legacy_registry_b),
    }


__all__ = ["verify_reduce"]
