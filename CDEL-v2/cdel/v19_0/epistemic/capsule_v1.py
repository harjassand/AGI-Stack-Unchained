"""Epistemic capsule assembly for v19.0 RE0->RE2 airlock."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ...v1_7r.canon import canon_bytes, write_canon_json
from ..common_v1 import (
    canon_hash_obj,
    ensure_sha256,
    fail,
    validate_schema,
    verify_object_id,
)
from ..world.merkle_v1 import compute_world_root
from ..world.sip_v1 import run_sip
from .certs_v1 import compute_epistemic_certs
from .instruction_strip_v1 import default_instruction_strip_contract
from .reduce_v1 import reduce_mobs_to_qxwmr_graph_with_strip, verify_mob_id, verify_mob_payload
from .retention_v1 import build_retention_artifacts
from .type_registry_v1 import build_type_binding, validate_type_registry
from .usable_index_v1 import append_usable_index_row


def _write_hashed_json(
    out_dir: Path,
    suffix: str,
    payload: dict[str, Any],
    *,
    id_field: str | None = None,
    float_tolerant: bool = False,
) -> tuple[Path, dict[str, Any], str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    obj = dict(payload)
    if id_field is not None:
        if float_tolerant:
            fail("SCHEMA_FAIL")
        no_id = dict(obj)
        no_id.pop(id_field, None)
        obj[id_field] = canon_hash_obj(no_id)
    if float_tolerant:
        blob = _float_tolerant_canon_bytes(obj)
        digest = "sha256:" + hashlib.sha256(blob).hexdigest()
    else:
        blob = canon_bytes(obj)
        digest = canon_hash_obj(obj)
    path = out_dir / f"sha256_{digest.split(':', 1)[1]}.{suffix}"
    if float_tolerant:
        path.write_bytes(blob + b"\n")
    else:
        write_canon_json(path, obj)
    return path, obj, digest


def _float_tolerant_canon_bytes(payload: dict[str, Any]) -> bytes:
    try:
        text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except Exception:  # noqa: BLE001
        fail("SCHEMA_FAIL")
        return b""
    return text.encode("utf-8")


def _load_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or not path.is_file():
        fail("MISSING_STATE_INPUT")
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:  # noqa: BLE001
            fail("SCHEMA_FAIL")
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        if canon_bytes(row) != line.encode("utf-8"):
            fail("NONDETERMINISTIC")
        validate_schema(row, "epistemic_episode_index_row_v1")
        expected_row_hash = canon_hash_obj({k: v for k, v in row.items() if k != "row_hash"})
        if str(row.get("row_hash", "")) != expected_row_hash:
            fail("INDEX_CHAIN_MISMATCH")
        rows.append(row)

    prev_hash: str | None = None
    for row in rows:
        prev_row_hash = row.get("prev_row_hash")
        if prev_hash is None:
            if prev_row_hash is not None:
                fail("INDEX_CHAIN_MISMATCH")
        else:
            if str(prev_row_hash) != prev_hash:
                fail("INDEX_CHAIN_MISMATCH")
        prev_hash = str(row.get("row_hash", ""))
    return rows


def _select_row(*, rows: list[dict[str, Any]], selector: dict[str, Any], tick_u64: int) -> dict[str, Any]:
    validate_schema(selector, "epistemic_episode_selector_v1")
    kind = str(selector.get("kind", "")).strip()
    eligible = [
        row
        for row in rows
        if bool(row.get("commit_ready_b", False))
        and bool(row.get("complete_b", False))
    ]
    if kind == "BY_EPISODE_ID":
        target = str(selector.get("episode_id", "")).strip()
        matches = [row for row in eligible if str(row.get("episode_id", "")) == target]
        if not matches:
            fail("INDEX_SELECTION_EMPTY")
        return matches[-1]
    if kind == "BY_TICK_U64":
        selector_tick = int(selector.get("tick_u64", tick_u64))
        bounded = [row for row in eligible if int(row.get("tick_u64", -1)) <= selector_tick]
        if not bounded:
            fail("INDEX_SELECTION_EMPTY")
        max_tick = max(int(row.get("tick_u64", -1)) for row in bounded)
        matches = [row for row in bounded if int(row.get("tick_u64", -1)) == max_tick]
        if not matches:
            fail("INDEX_SELECTION_EMPTY")
        return matches[-1]
    fail("SCHEMA_FAIL")
    return {}


def _load_hashed_object(
    path: Path,
    expected_hash: str,
    schema_name: str,
    id_field: str | None = None,
    *,
    require_id_derivation: bool = True,
) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        fail("MISSING_STATE_INPUT")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        fail("SCHEMA_FAIL")
    if not isinstance(payload, dict):
        fail("SCHEMA_FAIL")
    validate_schema(payload, schema_name)
    if id_field is not None:
        declared_text = ensure_sha256(payload.get(id_field), reason="SCHEMA_FAIL")
        if declared_text != expected_hash:
            fail("NONDETERMINISTIC")
        if require_id_derivation:
            declared = verify_object_id(payload, id_field=id_field)
            if declared != expected_hash:
                fail("NONDETERMINISTIC")
    elif canon_hash_obj(payload) != expected_hash:
        fail("NONDETERMINISTIC")
    return payload


def _load_mob_entry(
    *,
    outbox_root: Path,
    episode_dir: Path,
    mob_id: str,
) -> tuple[dict[str, Any], dict[str, Any] | None, bytes | None]:
    mob_suffix = mob_id.split(":", 1)[1]
    candidates = [
        episode_dir / "mobs" / f"sha256_{mob_suffix}.epistemic_model_output_v1.json",
        episode_dir / "mobs" / f"sha256_{mob_suffix}.epistemic_model_output_v2.json",
    ]
    existing = [path for path in candidates if path.exists() and path.is_file()]
    if len(existing) != 1:
        fail("MISSING_STATE_INPUT")
    path = existing[0]
    try:
        mob_payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        fail("SCHEMA_FAIL")
    if not isinstance(mob_payload, dict):
        fail("SCHEMA_FAIL")
    schema_version, observed_mob_id = verify_mob_payload(mob_payload)
    if observed_mob_id != mob_id:
        fail("NONDETERMINISTIC")
    if schema_version == "epistemic_model_output_v1":
        if str(mob_payload.get("content_kind", "")).strip() != "CANON_JSON":
            fail("MOB_FORMAT_REJECTED")
        return mob_payload, None, None

    mob_receipt_id = ensure_sha256(mob_payload.get("mob_receipt_id"), reason="SCHEMA_FAIL")
    receipt_path = episode_dir / "mobs" / f"sha256_{mob_receipt_id.split(':', 1)[1]}.epistemic_mob_receipt_v1.json"
    mob_receipt = _load_hashed_object(
        receipt_path,
        mob_receipt_id,
        "epistemic_mob_receipt_v1",
        id_field="mob_receipt_id",
    )
    if ensure_sha256(mob_receipt.get("mob_id"), reason="SCHEMA_FAIL") != mob_id:
        fail("NONDETERMINISTIC")
    if ensure_sha256(mob_receipt.get("episode_id"), reason="SCHEMA_FAIL") != ensure_sha256(
        mob_payload.get("episode_id"),
        reason="SCHEMA_FAIL",
    ):
        fail("NONDETERMINISTIC")

    mob_blob_id = ensure_sha256(mob_payload.get("mob_blob_id"), reason="SCHEMA_FAIL")
    if ensure_sha256(mob_receipt.get("mob_blob_id"), reason="SCHEMA_FAIL") != mob_blob_id:
        fail("NONDETERMINISTIC")
    blob_path = outbox_root / "blobs" / "sha256" / mob_blob_id.split(":", 1)[1]
    if not blob_path.exists() or not blob_path.is_file():
        fail("MISSING_STATE_INPUT")
    blob_bytes = blob_path.read_bytes()
    if "sha256:" + hashlib.sha256(blob_bytes).hexdigest() != mob_blob_id:
        fail("HASH_MISMATCH")
    return mob_payload, mob_receipt, blob_bytes


def _load_episode(
    *,
    outbox_root: Path,
    row: dict[str, Any],
) -> dict[str, Any]:
    episode_id = ensure_sha256(row.get("episode_id"), reason="SCHEMA_FAIL")
    episode_manifest_id = ensure_sha256(row.get("episode_manifest_id"), reason="SCHEMA_FAIL")
    pinset_id = ensure_sha256(row.get("pinset_id"), reason="SCHEMA_FAIL")
    episode_dir = outbox_root / "episodes" / episode_id
    if not episode_dir.exists() or not episode_dir.is_dir():
        fail("MISSING_STATE_INPUT")

    manifest_path = episode_dir / f"sha256_{episode_manifest_id.split(':', 1)[1]}.epistemic_episode_outbox_v1.json"
    manifest = _load_hashed_object(
        manifest_path,
        episode_manifest_id,
        "epistemic_episode_outbox_v1",
        id_field="episode_manifest_id",
        require_id_derivation=False,
    )

    marker_id = ensure_sha256(manifest.get("episode_complete_marker_id"), reason="SCHEMA_FAIL")
    marker_path = episode_dir / f"sha256_{marker_id.split(':', 1)[1]}.epistemic_episode_complete_marker_v1.json"
    marker = _load_hashed_object(
        marker_path,
        marker_id,
        "epistemic_episode_complete_marker_v1",
        id_field="marker_id",
    )
    if str(marker.get("episode_manifest_id", "")) != episode_manifest_id:
        fail("EPISODE_MARKER_MISMATCH")
    if not bool(marker.get("complete_b", False)):
        fail("EPISODE_NOT_COMPLETE")

    if bool(row.get("complete_b", False)) is not True or bool(row.get("commit_ready_b", False)) is not True:
        fail("EPISODE_NOT_COMPLETE")
    if bool(manifest.get("complete_b", False)) is not True or bool(manifest.get("commit_ready_b", False)) is not True:
        fail("EPISODE_NOT_COMPLETE")

    pinset_path = episode_dir / "pinset" / f"sha256_{pinset_id.split(':', 1)[1]}.epistemic_pinset_v1.json"
    pinset = _load_hashed_object(pinset_path, pinset_id, "epistemic_pinset_v1", id_field="pinset_id")

    mob_ids_raw = manifest.get("mob_ids")
    if not isinstance(mob_ids_raw, list) or not mob_ids_raw:
        fail("SCHEMA_FAIL")
    mob_payloads: list[dict[str, Any]] = []
    mob_receipts_by_id: dict[str, dict[str, Any]] = {}
    mob_blob_bytes_by_id: dict[str, bytes] = {}
    for mob_id_raw in mob_ids_raw:
        mob_id = ensure_sha256(mob_id_raw, reason="SCHEMA_FAIL")
        mob, mob_receipt, mob_blob = _load_mob_entry(
            outbox_root=outbox_root,
            episode_dir=episode_dir,
            mob_id=mob_id,
        )
        mob_payloads.append(mob)
        if isinstance(mob_receipt, dict):
            receipt_id = ensure_sha256(mob_receipt.get("mob_receipt_id"), reason="SCHEMA_FAIL")
            mob_receipts_by_id[receipt_id] = mob_receipt
        if mob_blob is not None:
            mob_blob_id = ensure_sha256(mob.get("mob_blob_id"), reason="SCHEMA_FAIL")
            mob_blob_bytes_by_id[mob_blob_id] = bytes(mob_blob)

    return {
        "episode_id": episode_id,
        "episode_dir": episode_dir,
        "index_row": row,
        "manifest": manifest,
        "marker": marker,
        "pinset": pinset,
        "mobs": mob_payloads,
        "mob_receipts_by_id": mob_receipts_by_id,
        "mob_blob_bytes_by_id": mob_blob_bytes_by_id,
    }


def _world_snapshot_payload(*, sip_profile_id: str, manifest_id: str, world_root: str, receipt_id: str, leakage_gate: dict[str, Any], non_interference_gate: dict[str, Any]) -> dict[str, Any]:
    provenance_policy_ref = canon_hash_obj(
        {
            "schema_name": "provenance_grades_policy_v1",
            "schema_version": "v19_0",
            "policy": "DEFAULT_TRUSTLESS",
        }
    )
    payload = {
        "schema_name": "world_snapshot_v1",
        "schema_version": "v19_0",
        "world_snapshot_id": "sha256:" + ("0" * 64),
        "sip_profile_id": sip_profile_id,
        "world_manifest_ref": manifest_id,
        "world_root": world_root,
        "provenance_grades_policy_ref": provenance_policy_ref,
        "non_interference_gate_receipt_ref": canon_hash_obj(non_interference_gate),
        "leakage_gate_receipt_ref": canon_hash_obj(leakage_gate),
        "ingestion_receipt_ref": receipt_id,
    }
    payload["world_snapshot_id"] = canon_hash_obj({k: v for k, v in payload.items() if k != "world_snapshot_id"})
    validate_schema(payload, "world_snapshot_v1")
    if str(payload.get("world_snapshot_id", "")) != canon_hash_obj({k: v for k, v in payload.items() if k != "world_snapshot_id"}):
        fail("NONDETERMINISTIC")
    return payload


def build_epistemic_capsule(
    *,
    tick_u64: int,
    outbox_root: Path,
    selector: dict[str, Any],
    accepted_mob_schema_versions: list[str] | None,
    reduce_contract: dict[str, Any],
    confidence_calibration: dict[str, Any],
    sip_profile: dict[str, Any],
    sip_budget_spec: dict[str, Any],
    type_registry: dict[str, Any] | None = None,
    type_provisionals: list[dict[str, Any]] | None = None,
    type_ratifications: list[dict[str, Any]] | None = None,
    objective_profile_id: str | None = None,
    cert_profile: dict[str, Any] | None = None,
    cert_gate_mode: str = "WARN",
    parent_type_registry: dict[str, Any] | None = None,
    retention_policy: dict[str, Any] | None = None,
    sampling_seed_u64: int | None = None,
    epistemic_kernel_spec: dict[str, Any] | None = None,
    instruction_strip_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cert_gate_mode = str(cert_gate_mode).strip().upper()
    if cert_gate_mode not in {"OFF", "WARN", "ENFORCE"}:
        fail("SCHEMA_FAIL")

    rows = _load_jsonl_rows(outbox_root / "index" / "epistemic_episode_index_v1.jsonl")
    selected = _select_row(rows=rows, selector=selector, tick_u64=tick_u64)
    episode = _load_episode(outbox_root=outbox_root, row=selected)

    type_registry_payload: dict[str, Any] | None = None
    type_registry_id: str | None = None
    if type_registry is not None:
        type_registry_payload = validate_type_registry(dict(type_registry))
        type_registry_id = ensure_sha256(type_registry_payload.get("registry_id"), reason="SCHEMA_FAIL")
    parent_type_registry_payload: dict[str, Any] | None = None
    if parent_type_registry is not None:
        parent_type_registry_payload = validate_type_registry(dict(parent_type_registry))

    cert_profile_payload: dict[str, Any] | None = None
    cert_profile_id = "sha256:" + ("0" * 64)
    if cert_profile is not None:
        cert_profile_payload = dict(cert_profile)
        validate_schema(cert_profile_payload, "epistemic_cert_profile_v1")
        cert_profile_id = verify_object_id(cert_profile_payload, id_field="cert_profile_id")

    if instruction_strip_contract is None:
        instruction_strip_contract_payload = default_instruction_strip_contract()
    else:
        instruction_strip_contract_payload = dict(instruction_strip_contract)
    validate_schema(instruction_strip_contract_payload, "epistemic_instruction_strip_contract_v1")
    instruction_strip_contract_id = verify_object_id(instruction_strip_contract_payload, id_field="contract_id")
    if ensure_sha256(reduce_contract.get("instruction_strip_contract_id"), reason="SCHEMA_FAIL") != instruction_strip_contract_id:
        fail("PIN_HASH_MISMATCH")

    reduce_result = reduce_mobs_to_qxwmr_graph_with_strip(
        episode_id=str(episode["episode_id"]),
        mob_payloads=list(episode["mobs"]),
        reduce_contract=reduce_contract,
        instruction_strip_contract=instruction_strip_contract_payload,
        calibration=confidence_calibration,
        accepted_mob_schema_versions=accepted_mob_schema_versions,
        mob_blob_bytes_by_id=dict(episode.get("mob_blob_bytes_by_id") or {}),
        mob_receipts_by_id=dict(episode.get("mob_receipts_by_id") or {}),
        type_registry_id=type_registry_id,
    )
    graph = dict(reduce_result.get("graph") or {})
    strip_receipts = [dict(row) for row in list(reduce_result.get("strip_receipts") or []) if isinstance(row, dict)]
    strip_receipt_id = ensure_sha256(reduce_result.get("strip_receipt_id"), reason="SCHEMA_FAIL")
    graph_id = verify_object_id(graph, id_field="graph_id")

    type_binding_payload: dict[str, Any] | None = None
    if type_registry_payload is not None:
        type_binding_payload = build_type_binding(
            graph=graph,
            type_registry=type_registry_payload,
            provisionals=list(type_provisionals or []),
            ratifications=list(type_ratifications or []),
        )
        if str(type_binding_payload.get("outcome", "")) != "ACCEPT":
            fail("TYPE_GOVERNANCE_FAIL")

    provisionals_sorted: list[dict[str, Any]] = []
    for row in list(type_provisionals or []):
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        validate_schema(row, "epistemic_type_provisional_v1")
        verify_object_id(row, id_field="provisional_id")
        provisionals_sorted.append(dict(row))
    provisionals_sorted.sort(key=lambda r: str(r.get("provisional_id", "")))

    ratifications_sorted: list[dict[str, Any]] = []
    for row in list(type_ratifications or []):
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        validate_schema(row, "epistemic_type_ratification_receipt_v1")
        verify_object_id(row, id_field="receipt_id")
        ratifications_sorted.append(dict(row))
    ratifications_sorted.sort(key=lambda r: str(r.get("receipt_id", "")))

    manifest_entries: list[dict[str, Any]] = []
    artifact_bytes_by_content_id: dict[str, bytes] = {}

    def _add_json_entry(
        *,
        logical_path: str,
        payload: dict[str, Any],
        schema_name: str,
        schema_version: str,
        artifact_id: str,
        content_kind: str = "CANON_JSON",
    ) -> None:
        artifact_id = ensure_sha256(artifact_id, reason="SCHEMA_FAIL")
        if content_kind == "CANON_JSON":
            blob = canon_bytes(payload)
            canon_version: str | None = "GCJ-1"
        elif content_kind == "RAW_BYTES":
            blob = _float_tolerant_canon_bytes(payload)
            canon_version = None
        else:
            fail("SCHEMA_FAIL")
            return
        content_id = "sha256:" + hashlib.sha256(blob).hexdigest()
        artifact_bytes_by_content_id[content_id] = blob
        entry = {
            "logical_path": logical_path,
            "content_id": content_id,
            "content_length_bytes": len(blob),
            "content_kind": content_kind,
            "content_artifact_ref": {
                "schema_name": schema_name,
                "schema_version": schema_version,
                "id": artifact_id,
            },
        }
        if content_kind == "CANON_JSON":
            entry["canon_version"] = "GCJ-1"
        else:
            entry["canon_version"] = canon_version
        manifest_entries.append(entry)

    def _add_bytes_entry(
        *,
        logical_path: str,
        blob: bytes,
        schema_name: str,
        schema_version: str,
        artifact_id: str,
    ) -> None:
        artifact_id = ensure_sha256(artifact_id, reason="SCHEMA_FAIL")
        content_id = "sha256:" + hashlib.sha256(blob).hexdigest()
        artifact_bytes_by_content_id[content_id] = bytes(blob)
        manifest_entries.append(
            {
                "logical_path": logical_path,
                "content_id": content_id,
                "content_length_bytes": len(blob),
                "content_kind": "RAW_BYTES",
                "canon_version": None,
                "content_artifact_ref": {
                    "schema_name": schema_name,
                    "schema_version": schema_version,
                    "id": artifact_id,
                },
            }
        )

    manifest_payload = dict(episode["manifest"])
    manifest_id_episode = ensure_sha256(manifest_payload.get("episode_manifest_id"), reason="SCHEMA_FAIL")
    if manifest_id_episode != str(selected.get("episode_manifest_id", "")):
        fail("NONDETERMINISTIC")
    pinset_payload = dict(episode["pinset"])
    pinset_id = verify_object_id(pinset_payload, id_field="pinset_id")

    _add_json_entry(
        logical_path="epistemic/episode_manifest.json",
        payload=manifest_payload,
        schema_name="epistemic_episode_outbox_v1",
        schema_version="epistemic_episode_outbox_v1",
        artifact_id=manifest_id_episode,
    )
    _add_json_entry(
        logical_path="epistemic/pinset.json",
        payload=pinset_payload,
        schema_name="epistemic_pinset_v1",
        schema_version="epistemic_pinset_v1",
        artifact_id=pinset_id,
    )
    mobs_sorted = sorted(episode["mobs"], key=lambda row: str(row.get("mob_id", "")))
    for idx, mob in enumerate(mobs_sorted):
        mob_id = verify_mob_id(mob)
        mob_schema = str(mob.get("schema_version", "")).strip()
        if mob_schema == "epistemic_model_output_v1":
            _add_json_entry(
                logical_path=f"epistemic/mobs/{idx:04d}.json",
                payload=mob,
                schema_name="epistemic_model_output_v1",
                schema_version="epistemic_model_output_v1",
                artifact_id=mob_id,
                content_kind="RAW_BYTES",
            )
            continue
        if mob_schema != "epistemic_model_output_v2":
            fail("MOB_SCHEMA_UNSUPPORTED")
        _add_json_entry(
            logical_path=f"epistemic/mobs/{idx:04d}.json",
            payload=mob,
            schema_name="epistemic_model_output_v2",
            schema_version="epistemic_model_output_v2",
            artifact_id=mob_id,
            content_kind="CANON_JSON",
        )
        mob_receipt_id = ensure_sha256(mob.get("mob_receipt_id"), reason="SCHEMA_FAIL")
        mob_receipt = dict((episode.get("mob_receipts_by_id") or {}).get(mob_receipt_id) or {})
        if not mob_receipt:
            fail("MISSING_STATE_INPUT")
        _add_json_entry(
            logical_path=f"epistemic/mob_receipts/{idx:04d}.json",
            payload=mob_receipt,
            schema_name="epistemic_mob_receipt_v1",
            schema_version="epistemic_mob_receipt_v1",
            artifact_id=mob_receipt_id,
            content_kind="CANON_JSON",
        )
        mob_blob_id = ensure_sha256(mob.get("mob_blob_id"), reason="SCHEMA_FAIL")
        mob_blob = (episode.get("mob_blob_bytes_by_id") or {}).get(mob_blob_id)
        if mob_blob is None:
            fail("MISSING_STATE_INPUT")
        _add_bytes_entry(
            logical_path=f"epistemic/mob_blobs/{idx:04d}.bin",
            blob=bytes(mob_blob),
            schema_name="epistemic_mob_blob_v1",
            schema_version="binary",
            artifact_id=mob_blob_id,
        )
    _add_json_entry(
        logical_path="epistemic/contracts/instruction_strip_contract.json",
        payload=instruction_strip_contract_payload,
        schema_name="epistemic_instruction_strip_contract_v1",
        schema_version="epistemic_instruction_strip_contract_v1",
        artifact_id=instruction_strip_contract_id,
    )
    for idx, strip_receipt in enumerate(strip_receipts):
        strip_receipt_id_row = verify_object_id(strip_receipt, id_field="receipt_id")
        _add_json_entry(
            logical_path=f"epistemic/strip_receipts/{idx:04d}.json",
            payload=strip_receipt,
            schema_name="epistemic_instruction_strip_receipt_v1",
            schema_version="epistemic_instruction_strip_receipt_v1",
            artifact_id=strip_receipt_id_row,
        )
    _add_json_entry(
        logical_path="epistemic/distillate/qxwmr_graph.json",
        payload=graph,
        schema_name="qxwmr_graph_v1",
        schema_version="qxwmr_graph_v1",
        artifact_id=graph_id,
    )
    if type_registry_payload is not None:
        registry_id = verify_object_id(type_registry_payload, id_field="registry_id")
        _add_json_entry(
            logical_path="epistemic/type/registry.json",
            payload=type_registry_payload,
            schema_name="epistemic_type_registry_v1",
            schema_version="epistemic_type_registry_v1",
            artifact_id=registry_id,
        )
    for idx, provisional in enumerate(provisionals_sorted):
        provisional_id = verify_object_id(provisional, id_field="provisional_id")
        _add_json_entry(
            logical_path=f"epistemic/type/provisionals/{idx:04d}.json",
            payload=provisional,
            schema_name="epistemic_type_provisional_v1",
            schema_version="epistemic_type_provisional_v1",
            artifact_id=provisional_id,
        )
    for idx, ratification in enumerate(ratifications_sorted):
        receipt_id = verify_object_id(ratification, id_field="receipt_id")
        _add_json_entry(
            logical_path=f"epistemic/type/ratifications/{idx:04d}.json",
            payload=ratification,
            schema_name="epistemic_type_ratification_receipt_v1",
            schema_version="epistemic_type_ratification_receipt_v1",
            artifact_id=receipt_id,
        )
    if type_binding_payload is not None:
        binding_id = verify_object_id(type_binding_payload, id_field="binding_id")
        _add_json_entry(
            logical_path="epistemic/type/binding.json",
            payload=type_binding_payload,
            schema_name="epistemic_type_binding_v1",
            schema_version="epistemic_type_binding_v1",
            artifact_id=binding_id,
        )
    if epistemic_kernel_spec is not None:
        validate_schema(epistemic_kernel_spec, "epistemic_kernel_spec_v1")
        kernel_spec_id = verify_object_id(epistemic_kernel_spec, id_field="kernel_spec_id")
        _add_json_entry(
            logical_path="epistemic/kernel/spec.json",
            payload=dict(epistemic_kernel_spec),
            schema_name="epistemic_kernel_spec_v1",
            schema_version="epistemic_kernel_spec_v1",
            artifact_id=kernel_spec_id,
        )

    manifest = {
        "schema_name": "world_snapshot_manifest_v1",
        "schema_version": "v19_0",
        "manifest_id": "sha256:" + ("0" * 64),
        "path_normalization": "NFC_FORWARD_SLASH",
        "ordering_rule": "UNICODE_CODEPOINT_THEN_UTF8_BYTES",
        "entries": sorted(manifest_entries, key=lambda row: str(row.get("logical_path", ""))),
    }
    manifest["manifest_id"] = canon_hash_obj({k: v for k, v in manifest.items() if k != "manifest_id"})
    validate_schema(manifest, "world_snapshot_manifest_v1")
    manifest_id = verify_object_id(manifest, id_field="manifest_id")

    world_root = compute_world_root(manifest, enforce_sorted=True)

    sip_profile_id = ensure_sha256(sip_profile.get("sip_profile_id"), reason="SCHEMA_FAIL")
    sip_receipt = run_sip(
        manifest=manifest,
        artifact_bytes_by_content_id=artifact_bytes_by_content_id,
        sip_profile=sip_profile,
        world_task_bindings=[],
        world_snapshot_id="sha256:" + ("0" * 64),
        budget_spec=sip_budget_spec,
    )
    validate_schema(sip_receipt, "sealed_ingestion_receipt_v1")
    sip_receipt_id = verify_object_id(sip_receipt, id_field="receipt_id")
    sip_outcome = str(sip_receipt.get("outcome", "")).strip()
    if sip_outcome == "REJECT":
        fail("SIP_REJECTED")
    if sip_outcome != "ACCEPT":
        fail("SIP_SAFE_HALT")
    if str(sip_receipt.get("computed_world_root", "")) != world_root:
        fail("NONDETERMINISTIC")

    world_snapshot = _world_snapshot_payload(
        sip_profile_id=sip_profile_id,
        manifest_id=manifest_id,
        world_root=world_root,
        receipt_id=sip_receipt_id,
        leakage_gate=dict((sip_receipt.get("gate_results") or {}).get("leakage_gate") or {}),
        non_interference_gate=dict((sip_receipt.get("gate_results") or {}).get("non_interference_gate") or {}),
    )

    base_capsule_payload = {
        "schema_version": "epistemic_capsule_v1",
        "capsule_id": "sha256:" + ("0" * 64),
        "episode_id": str(episode["episode_id"]),
        "tick_u64": int(tick_u64),
        "pinset_id": pinset_id,
        "mob_ids": [str(row.get("mob_id", "")) for row in sorted(episode["mobs"], key=lambda x: str(x.get("mob_id", "")))],
        "distillate_graph_id": graph_id,
        "strip_receipt_id": strip_receipt_id,
        "reduce_contract_id": verify_object_id(reduce_contract, id_field="contract_id"),
        "confidence_calibration_id": verify_object_id(confidence_calibration, id_field="calibration_id"),
        "sip_manifest_id": manifest_id,
        "sip_receipt_id": sip_receipt_id,
        "world_snapshot_id": str(world_snapshot.get("world_snapshot_id", "")),
        "world_root": world_root,
        "cert_profile_id": cert_profile_id,
    }
    if type_registry_payload is not None:
        base_capsule_payload["type_registry_id"] = ensure_sha256(type_registry_payload.get("registry_id"), reason="SCHEMA_FAIL")
    if type_binding_payload is not None:
        base_capsule_payload["type_binding_id"] = ensure_sha256(type_binding_payload.get("binding_id"), reason="SCHEMA_FAIL")

    def _materialize_capsule(*, usable_b: bool, cert_gate_status: str) -> dict[str, Any]:
        payload = dict(base_capsule_payload)
        payload["usable_b"] = bool(usable_b)
        payload["cert_gate_status"] = str(cert_gate_status)
        payload["capsule_id"] = canon_hash_obj({k: v for k, v in payload.items() if k != "capsule_id"})
        validate_schema(payload, "epistemic_capsule_v1")
        verify_object_id(payload, id_field="capsule_id")
        return payload

    objective_profile_sha = ensure_sha256(
        objective_profile_id if objective_profile_id is not None else ("sha256:" + ("0" * 64)),
        reason="SCHEMA_FAIL",
    )
    cert_reason_code = "CERT_OK"
    final_usable_b = True
    final_cert_gate_status = "PASS"
    ecac_payload: dict[str, Any] | None = None
    eufc_payload: dict[str, Any] | None = None
    probe_capsule = _materialize_capsule(usable_b=True, cert_gate_status="PASS")
    if cert_gate_mode == "OFF":
        final_usable_b = True
        final_cert_gate_status = "PASS"
        cert_reason_code = "GATE_OFF"
    elif type_binding_payload is None:
        final_usable_b = cert_gate_mode != "ENFORCE"
        final_cert_gate_status = "BLOCKED" if cert_gate_mode == "ENFORCE" else "WARN"
        cert_reason_code = "TYPE_BINDING_MISSING"
    elif cert_profile_payload is None:
        final_usable_b = cert_gate_mode != "ENFORCE"
        final_cert_gate_status = "BLOCKED" if cert_gate_mode == "ENFORCE" else "WARN"
        cert_reason_code = "CERT_PROFILE_MISSING"
    else:
        try:
            probe = compute_epistemic_certs(
                capsule=probe_capsule,
                graph=graph,
                type_binding=type_binding_payload,
                objective_profile_id=objective_profile_sha,
                cert_profile=cert_profile_payload,
            )
            probe_ok = (
                str((probe.get("ecac") or {}).get("status", "")) == "OK"
                and str((probe.get("eufc") or {}).get("status", "")) == "OK"
            )
            if probe_ok:
                final_usable_b = True
                final_cert_gate_status = "PASS"
                cert_reason_code = "CERT_OK"
            elif cert_gate_mode == "ENFORCE":
                final_usable_b = False
                final_cert_gate_status = "BLOCKED"
                cert_reason_code = "CERT_PREDICATE_FAIL"
            else:
                final_usable_b = True
                final_cert_gate_status = "WARN"
                cert_reason_code = "CERT_PREDICATE_WARN"
        except Exception:  # noqa: BLE001
            if cert_gate_mode == "ENFORCE":
                final_usable_b = False
                final_cert_gate_status = "BLOCKED"
            else:
                final_usable_b = True
                final_cert_gate_status = "WARN"
            cert_reason_code = "CERT_COMPUTE_FAIL"

    capsule = _materialize_capsule(usable_b=final_usable_b, cert_gate_status=final_cert_gate_status)
    if cert_gate_mode != "OFF" and type_binding_payload is not None and cert_profile_payload is not None:
        try:
            certs = compute_epistemic_certs(
                capsule=capsule,
                graph=graph,
                type_binding=type_binding_payload,
                objective_profile_id=objective_profile_sha,
                cert_profile=cert_profile_payload,
            )
            ecac_payload = dict(certs["ecac"])
            eufc_payload = dict(certs["eufc"])
        except Exception:  # noqa: BLE001
            if cert_gate_mode == "ENFORCE":
                capsule = _materialize_capsule(usable_b=False, cert_gate_status="BLOCKED")
                cert_reason_code = "CERT_COMPUTE_FAIL"

    retention_policy_payload: dict[str, Any] | None = None
    retention_artifacts: dict[str, dict[str, Any]] | None = None
    if retention_policy is not None:
        retention_policy_payload = dict(retention_policy)
        validate_schema(retention_policy_payload, "epistemic_retention_policy_v1")
        verify_object_id(retention_policy_payload, id_field="policy_id")
        retention_artifacts = build_retention_artifacts(
            retention_policy=retention_policy_payload,
            capsule=capsule,
            world_manifest=manifest,
            sampling_seed_u64=int(tick_u64 if sampling_seed_u64 is None else sampling_seed_u64),
        )

    return {
        "selected_index_row": selected,
        "selector": selector,
        "accepted_mob_schema_versions": list(accepted_mob_schema_versions or ["epistemic_model_output_v1"]),
        "episode_manifest": manifest_payload,
        "episode_marker": dict(episode["marker"]),
        "pinset": pinset_payload,
        "mobs": list(episode["mobs"]),
        "mob_receipts_by_id": dict(episode.get("mob_receipts_by_id") or {}),
        "mob_blob_bytes_by_id": dict(episode.get("mob_blob_bytes_by_id") or {}),
        "reduce_contract": reduce_contract,
        "instruction_strip_contract": instruction_strip_contract_payload,
        "strip_receipts": strip_receipts,
        "strip_receipt_id": strip_receipt_id,
        "confidence_calibration": confidence_calibration,
        "sip_profile": sip_profile,
        "sip_budget_spec": sip_budget_spec,
        "graph": graph,
        "type_registry": type_registry_payload,
        "type_binding": type_binding_payload,
        "parent_type_registry": parent_type_registry_payload,
        "type_provisionals": provisionals_sorted,
        "type_ratifications": ratifications_sorted,
        "objective_profile_id": objective_profile_sha,
        "cert_profile": cert_profile_payload,
        "cert_profile_id": cert_profile_id,
        "cert_gate_mode": cert_gate_mode,
        "cert_reason_code": cert_reason_code,
        "epistemic_ecac": ecac_payload,
        "epistemic_eufc": eufc_payload,
        "retention_policy": retention_policy_payload,
        "retention_artifacts": retention_artifacts,
        "epistemic_kernel_spec": (dict(epistemic_kernel_spec) if isinstance(epistemic_kernel_spec, dict) else None),
        "world_manifest": manifest,
        "sip_receipt": sip_receipt,
        "world_snapshot": world_snapshot,
        "capsule": capsule,
    }


def write_capsule_bundle(*, state_root: Path, bundle: dict[str, Any]) -> dict[str, str]:
    epi_root = state_root / "epistemic"
    graph_path, _graph_obj, graph_hash = _write_hashed_json(
        epi_root / "graphs",
        "qxwmr_graph_v1.json",
        dict(bundle["graph"]),
        id_field="graph_id",
    )
    manifest_path, _manifest_obj, manifest_hash = _write_hashed_json(
        epi_root / "world" / "manifests",
        "world_snapshot_manifest_v1.json",
        dict(bundle["world_manifest"]),
        id_field="manifest_id",
    )
    receipt_path, _receipt_obj, receipt_hash = _write_hashed_json(
        epi_root / "world" / "receipts",
        "sealed_ingestion_receipt_v1.json",
        dict(bundle["sip_receipt"]),
        id_field="receipt_id",
    )
    snapshot_path, _snapshot_obj, snapshot_hash = _write_hashed_json(
        epi_root / "world" / "snapshots",
        "world_snapshot_v1.json",
        dict(bundle["world_snapshot"]),
        id_field="world_snapshot_id",
    )
    capsule_payload = dict(bundle["capsule"])
    capsule_path, _capsule_obj, capsule_hash = _write_hashed_json(
        epi_root / "capsules",
        "epistemic_capsule_v1.json",
        capsule_payload,
        id_field="capsule_id",
    )

    type_registry_hash = ""
    type_binding_hash = ""
    ecac_hash = ""
    eufc_hash = ""
    deletion_plan_hash = ""
    sampling_manifest_hash = ""
    summary_proof_hash = ""
    kernel_spec_hash = ""
    cert_profile_hash = ""
    strip_receipt_set_hash = ""

    instruction_strip_contract_payload = bundle.get("instruction_strip_contract")
    if isinstance(instruction_strip_contract_payload, dict):
        _write_hashed_json(
            epi_root / "contracts",
            "epistemic_instruction_strip_contract_v1.json",
            dict(instruction_strip_contract_payload),
            id_field="contract_id",
        )
    strip_receipts = [dict(row) for row in list(bundle.get("strip_receipts") or []) if isinstance(row, dict)]
    strip_receipt_rows_sorted = sorted(strip_receipts, key=lambda row: str(row.get("receipt_id", "")))
    for strip_receipt in strip_receipt_rows_sorted:
        _write_hashed_json(
            epi_root / "strip_receipts",
            "epistemic_instruction_strip_receipt_v1.json",
            dict(strip_receipt),
            id_field="receipt_id",
        )
    if strip_receipt_rows_sorted:
        strip_receipt_set_hash = canon_hash_obj(
            {
                "schema_version": "epistemic_instruction_strip_receipt_set_v1",
                "receipt_ids": [str(row.get("receipt_id", "")) for row in strip_receipt_rows_sorted],
            }
        )
        if ensure_sha256(capsule_payload.get("strip_receipt_id"), reason="SCHEMA_FAIL") != strip_receipt_set_hash:
            fail("NONDETERMINISTIC")

    type_registry_payload = bundle.get("type_registry")
    if isinstance(type_registry_payload, dict):
        _type_registry_path, _type_registry_obj, type_registry_hash = _write_hashed_json(
            epi_root / "type_registry",
            "epistemic_type_registry_v1.json",
            dict(type_registry_payload),
            id_field="registry_id",
        )

    for provisional in list(bundle.get("type_provisionals") or []):
        if isinstance(provisional, dict):
            _write_hashed_json(
                epi_root / "type" / "provisionals",
                "epistemic_type_provisional_v1.json",
                dict(provisional),
                id_field="provisional_id",
            )

    for ratification in list(bundle.get("type_ratifications") or []):
        if isinstance(ratification, dict):
            _write_hashed_json(
                epi_root / "type" / "ratifications",
                "epistemic_type_ratification_receipt_v1.json",
                dict(ratification),
                id_field="receipt_id",
            )

    type_binding_payload = bundle.get("type_binding")
    if isinstance(type_binding_payload, dict):
        _type_binding_path, _type_binding_obj, type_binding_hash = _write_hashed_json(
            epi_root / "type_bindings",
            "epistemic_type_binding_v1.json",
            dict(type_binding_payload),
            id_field="binding_id",
        )

    ecac_payload = bundle.get("epistemic_ecac")
    if isinstance(ecac_payload, dict):
        _ecac_path, _ecac_obj, ecac_hash = _write_hashed_json(
            epi_root / "certs",
            "epistemic_ecac_v1.json",
            dict(ecac_payload),
            id_field="ecac_id",
        )
    eufc_payload = bundle.get("epistemic_eufc")
    if isinstance(eufc_payload, dict):
        _eufc_path, _eufc_obj, eufc_hash = _write_hashed_json(
            epi_root / "certs",
            "epistemic_eufc_v1.json",
            dict(eufc_payload),
            id_field="eufc_id",
        )
    cert_profile_payload = bundle.get("cert_profile")
    if isinstance(cert_profile_payload, dict):
        _cert_profile_path, _cert_profile_obj, cert_profile_hash = _write_hashed_json(
            epi_root / "certs" / "profiles",
            "epistemic_cert_profile_v1.json",
            dict(cert_profile_payload),
            id_field="cert_profile_id",
        )

    if bool(capsule_payload.get("usable_b", False)):
        cert_profile_id = str(capsule_payload.get("cert_profile_id", "sha256:" + ("0" * 64)))
        _ = append_usable_index_row(
            state_root=state_root,
            capsule_id=ensure_sha256(capsule_payload.get("capsule_id"), reason="SCHEMA_FAIL"),
            distillate_graph_id=ensure_sha256(capsule_payload.get("distillate_graph_id"), reason="SCHEMA_FAIL"),
            usable_b=True,
            cert_gate_status=str(capsule_payload.get("cert_gate_status", "PASS")).strip().upper(),
            cert_profile_id=ensure_sha256(cert_profile_id, reason="SCHEMA_FAIL"),
            reason_code=str(bundle.get("cert_reason_code", "CERT_OK")),
        )

    retention_policy_payload = bundle.get("retention_policy")
    if isinstance(retention_policy_payload, dict):
        _write_hashed_json(
            epi_root / "retention",
            "epistemic_retention_policy_v1.json",
            dict(retention_policy_payload),
            id_field="policy_id",
        )
    retention_artifacts = bundle.get("retention_artifacts")
    if isinstance(retention_artifacts, dict):
        deletion_payload = retention_artifacts.get("deletion_plan")
        if isinstance(deletion_payload, dict):
            _deletion_path, _deletion_obj, deletion_plan_hash = _write_hashed_json(
                epi_root / "retention",
                "epistemic_deletion_plan_v1.json",
                dict(deletion_payload),
                id_field="plan_id",
            )
        sampling_payload = retention_artifacts.get("sampling_manifest")
        if isinstance(sampling_payload, dict):
            _sampling_path, _sampling_obj, sampling_manifest_hash = _write_hashed_json(
                epi_root / "retention",
                "epistemic_sampling_manifest_v1.json",
                dict(sampling_payload),
                id_field="manifest_id",
            )
        summary_payload = retention_artifacts.get("summary_proof")
        if isinstance(summary_payload, dict):
            _summary_path, _summary_obj, summary_proof_hash = _write_hashed_json(
                epi_root / "retention",
                "epistemic_summary_proof_v1.json",
                dict(summary_payload),
                id_field="proof_id",
            )

    kernel_spec_payload = bundle.get("epistemic_kernel_spec")
    if isinstance(kernel_spec_payload, dict):
        _kernel_path, _kernel_obj, kernel_spec_hash = _write_hashed_json(
            epi_root / "kernels" / "specs",
            "epistemic_kernel_spec_v1.json",
            dict(kernel_spec_payload),
            id_field="kernel_spec_id",
        )

    replay_root = epi_root / "replay_inputs"
    _write_hashed_json(
        replay_root / "index_row",
        "epistemic_episode_index_row_v1.json",
        dict(bundle["selected_index_row"]),
    )
    _write_hashed_json(
        replay_root / "selector",
        "epistemic_episode_selector_v1.json",
        dict(bundle["selector"]),
    )
    _write_hashed_json(
        replay_root / "contracts",
        "accepted_mob_schema_versions_v1.json",
        {
            "schema_version": "accepted_mob_schema_versions_v1",
            "accepted_mob_schema_versions": list(bundle.get("accepted_mob_schema_versions") or ["epistemic_model_output_v1"]),
        },
    )
    _write_hashed_json(
        replay_root / "episode",
        "epistemic_episode_outbox_v1.json",
        dict(bundle["episode_manifest"]),
        id_field="episode_manifest_id",
    )
    _write_hashed_json(
        replay_root / "episode",
        "epistemic_episode_complete_marker_v1.json",
        dict(bundle["episode_marker"]),
        id_field="marker_id",
    )
    _write_hashed_json(
        replay_root / "episode",
        "epistemic_pinset_v1.json",
        dict(bundle["pinset"]),
        id_field="pinset_id",
    )
    mob_receipts_by_id = dict(bundle.get("mob_receipts_by_id") or {})
    mob_blob_bytes_by_id = dict(bundle.get("mob_blob_bytes_by_id") or {})
    for mob in bundle["mobs"]:
        schema_version = str((mob or {}).get("schema_version", "")).strip()
        if schema_version == "epistemic_model_output_v1":
            _write_hashed_json(
                replay_root / "mobs",
                "epistemic_model_output_v1.json",
                dict(mob),
                float_tolerant=True,
            )
            continue
        if schema_version != "epistemic_model_output_v2":
            fail("MOB_SCHEMA_UNSUPPORTED")
        _write_hashed_json(
            replay_root / "mobs",
            "epistemic_model_output_v2.json",
            dict(mob),
            id_field=None,
        )
        receipt_id = ensure_sha256(mob.get("mob_receipt_id"), reason="SCHEMA_FAIL")
        receipt_payload = dict(mob_receipts_by_id.get(receipt_id) or {})
        if not receipt_payload:
            fail("MISSING_STATE_INPUT")
        _write_hashed_json(
            replay_root / "mob_receipts",
            "epistemic_mob_receipt_v1.json",
            receipt_payload,
            id_field="mob_receipt_id",
        )
        blob_id = ensure_sha256(mob.get("mob_blob_id"), reason="SCHEMA_FAIL")
        blob = mob_blob_bytes_by_id.get(blob_id)
        if blob is None:
            fail("MISSING_STATE_INPUT")
        blob_path = replay_root / "mob_blobs" / "sha256" / blob_id.split(":", 1)[1]
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        blob_path.write_bytes(bytes(blob))
    _write_hashed_json(
        replay_root / "contracts",
        "epistemic_reduce_contract_v1.json",
        dict(bundle["reduce_contract"]),
        id_field="contract_id",
    )
    instruction_strip_contract_payload = bundle.get("instruction_strip_contract")
    if isinstance(instruction_strip_contract_payload, dict):
        _write_hashed_json(
            replay_root / "contracts",
            "epistemic_instruction_strip_contract_v1.json",
            dict(instruction_strip_contract_payload),
            id_field="contract_id",
        )
    _write_hashed_json(
        replay_root / "contracts",
        "epistemic_confidence_calibration_v1.json",
        dict(bundle["confidence_calibration"]),
        id_field="calibration_id",
    )
    for strip_receipt in sorted(
        [dict(row) for row in list(bundle.get("strip_receipts") or []) if isinstance(row, dict)],
        key=lambda row: str(row.get("receipt_id", "")),
    ):
        _write_hashed_json(
            replay_root / "strip_receipts",
            "epistemic_instruction_strip_receipt_v1.json",
            strip_receipt,
            id_field="receipt_id",
        )
    type_registry_payload = bundle.get("type_registry")
    if isinstance(type_registry_payload, dict):
        _write_hashed_json(
            replay_root / "contracts",
            "epistemic_type_registry_v1.json",
            dict(type_registry_payload),
            id_field="registry_id",
        )
    parent_type_registry_payload = bundle.get("parent_type_registry")
    if isinstance(parent_type_registry_payload, dict):
        _write_hashed_json(
            replay_root / "contracts",
            "epistemic_type_registry_parent_v1.json",
            dict(parent_type_registry_payload),
            id_field="registry_id",
        )
    retention_policy_payload = bundle.get("retention_policy")
    if isinstance(retention_policy_payload, dict):
        _write_hashed_json(
            replay_root / "contracts",
            "epistemic_retention_policy_v1.json",
            dict(retention_policy_payload),
            id_field="policy_id",
        )
    _write_hashed_json(
        replay_root / "contracts",
        "epistemic_cert_gate_binding_v1.json",
        {
            "schema_version": "epistemic_cert_gate_binding_v1",
            "cert_gate_mode": str(bundle.get("cert_gate_mode", "OFF")),
            "objective_profile_id": str(bundle.get("objective_profile_id", "sha256:" + ("0" * 64))),
            "cert_profile_id": str(bundle.get("cert_profile_id", "sha256:" + ("0" * 64))),
            "cert_reason_code": str(bundle.get("cert_reason_code", "UNKNOWN")),
        },
    )
    cert_profile_payload = bundle.get("cert_profile")
    if isinstance(cert_profile_payload, dict):
        _write_hashed_json(
            replay_root / "contracts",
            "epistemic_cert_profile_v1.json",
            dict(cert_profile_payload),
            id_field="cert_profile_id",
        )
    type_binding_payload = bundle.get("type_binding")
    if isinstance(type_binding_payload, dict):
        _write_hashed_json(
            replay_root / "type",
            "epistemic_type_binding_v1.json",
            dict(type_binding_payload),
            id_field="binding_id",
        )
    for provisional in list(bundle.get("type_provisionals") or []):
        if isinstance(provisional, dict):
            _write_hashed_json(
                replay_root / "type" / "provisionals",
                "epistemic_type_provisional_v1.json",
                dict(provisional),
                id_field="provisional_id",
            )
    for ratification in list(bundle.get("type_ratifications") or []):
        if isinstance(ratification, dict):
            _write_hashed_json(
                replay_root / "type" / "ratifications",
                "epistemic_type_ratification_receipt_v1.json",
                dict(ratification),
                id_field="receipt_id",
            )
    ecac_payload = bundle.get("epistemic_ecac")
    if isinstance(ecac_payload, dict):
        _write_hashed_json(
            replay_root / "certs",
            "epistemic_ecac_v1.json",
            dict(ecac_payload),
            id_field="ecac_id",
        )
    eufc_payload = bundle.get("epistemic_eufc")
    if isinstance(eufc_payload, dict):
        _write_hashed_json(
            replay_root / "certs",
            "epistemic_eufc_v1.json",
            dict(eufc_payload),
            id_field="eufc_id",
        )
    retention_artifacts = bundle.get("retention_artifacts")
    if isinstance(retention_artifacts, dict):
        deletion_payload = retention_artifacts.get("deletion_plan")
        if isinstance(deletion_payload, dict):
            _write_hashed_json(
                replay_root / "retention",
                "epistemic_deletion_plan_v1.json",
                dict(deletion_payload),
                id_field="plan_id",
            )
        sampling_payload = retention_artifacts.get("sampling_manifest")
        if isinstance(sampling_payload, dict):
            _write_hashed_json(
                replay_root / "retention",
                "epistemic_sampling_manifest_v1.json",
                dict(sampling_payload),
                id_field="manifest_id",
            )
        summary_payload = retention_artifacts.get("summary_proof")
        if isinstance(summary_payload, dict):
            _write_hashed_json(
                replay_root / "retention",
                "epistemic_summary_proof_v1.json",
                dict(summary_payload),
                id_field="proof_id",
            )
    kernel_spec_payload = bundle.get("epistemic_kernel_spec")
    if isinstance(kernel_spec_payload, dict):
        _write_hashed_json(
            replay_root / "kernel",
            "epistemic_kernel_spec_v1.json",
            dict(kernel_spec_payload),
            id_field="kernel_spec_id",
        )
    _write_hashed_json(
        replay_root / "sip",
        "epistemic_sip_profile_v1.json",
        dict(bundle["sip_profile"]),
    )
    _write_hashed_json(
        replay_root / "sip",
        "budget_spec_v1.json",
        dict(bundle["sip_budget_spec"]),
    )

    return {
        "graph_hash": graph_hash,
        "world_manifest_hash": manifest_hash,
        "sip_receipt_hash": receipt_hash,
        "world_snapshot_hash": snapshot_hash,
        "capsule_hash": capsule_hash,
        "type_registry_hash": type_registry_hash or None,
        "type_binding_hash": type_binding_hash or None,
        "epistemic_ecac_hash": ecac_hash or None,
        "epistemic_eufc_hash": eufc_hash or None,
        "retention_deletion_plan_hash": deletion_plan_hash or None,
        "retention_sampling_manifest_hash": sampling_manifest_hash or None,
        "retention_summary_proof_hash": summary_proof_hash or None,
        "epistemic_kernel_spec_hash": kernel_spec_hash or None,
        "epistemic_cert_profile_hash": cert_profile_hash or None,
        "epistemic_strip_receipt_set_hash": strip_receipt_set_hash or None,
        "graph_path": str(graph_path),
        "world_manifest_path": str(manifest_path),
        "sip_receipt_path": str(receipt_path),
        "world_snapshot_path": str(snapshot_path),
        "capsule_path": str(capsule_path),
    }


__all__ = ["build_epistemic_capsule", "write_capsule_bundle"]
