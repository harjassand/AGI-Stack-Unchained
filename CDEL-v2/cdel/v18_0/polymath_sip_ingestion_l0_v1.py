"""Deterministic SIP-backed L0 ingestion for pinned local JSONL datasets (v1)."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

from cdel.v19_0.world.sip_v1 import run_sip

from ..v1_7r.canon import canon_bytes, loads
from .omega_common_v1 import (
    OmegaV18Error,
    canon_hash_obj,
    fail,
    hash_file_stream,
    require_relpath,
    validate_schema,
    write_hashed_json,
)

_PACK_SCHEMA_VERSION = "rsi_polymath_sip_ingestion_l0_pack_v1"
_CANON_JSONL_POLICY_ID = "CANON_JSONL_DETERMINISTIC_V1"
_ZERO_SHA256 = "sha256:" + ("0" * 64)


def _ensure_sha256(value: Any) -> str:
    text = str(value).strip()
    if len(text) != 71 or not text.startswith("sha256:"):
        fail("SCHEMA_FAIL")
    digest = text.split(":", 1)[1]
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        fail("SCHEMA_FAIL")
    return text


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _entropy_q16(data: bytes) -> int:
    if not data:
        return 0
    counts = [0] * 256
    for byte in data:
        counts[byte] += 1
    total = len(data)
    entropy = 0.0
    for count in counts:
        if count == 0:
            continue
        p = count / total
        entropy -= p * math.log2(p)
    return int(round(entropy * (1 << 16)))


def _subrun_root_from_state(state_root: Path) -> Path:
    state_abs = state_root.resolve()
    if len(state_abs.parents) < 3:
        fail("SCHEMA_FAIL")
    return state_abs.parents[2]


def _relpath_from_subrun(*, subrun_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(subrun_root.resolve()).as_posix()
    except ValueError:
        fail("SCHEMA_FAIL")
    return ""


def _normalize_pack(config: dict[str, Any]) -> dict[str, Any]:
    payload = dict(config)
    if str(payload.get("schema_version", "")).strip() != _PACK_SCHEMA_VERSION:
        fail("SCHEMA_FAIL")
    validate_schema(payload, _PACK_SCHEMA_VERSION)

    dataset_name = str(payload.get("dataset_name", "")).strip()
    if not dataset_name:
        fail("SCHEMA_FAIL")

    canonical_jsonl_policy = str(payload.get("canonical_jsonl_policy", "")).strip()
    if canonical_jsonl_policy != _CANON_JSONL_POLICY_ID:
        fail("SCHEMA_FAIL")

    inputs_raw = payload.get("inputs_relpaths")
    if not isinstance(inputs_raw, list) or not inputs_raw:
        fail("SCHEMA_FAIL")
    inputs_relpaths = sorted({require_relpath(row) for row in inputs_raw})

    pins_raw = payload.get("input_content_ids")
    if not isinstance(pins_raw, dict):
        fail("SCHEMA_FAIL")
    pins: dict[str, str] = {}
    for rel in inputs_relpaths:
        if rel not in pins_raw:
            fail("SCHEMA_FAIL")
        pins[rel] = _ensure_sha256(pins_raw.get(rel))

    sip_profile = payload.get("sip_profile")
    sip_budget_spec = payload.get("sip_budget_spec")
    if not isinstance(sip_profile, dict) or not isinstance(sip_budget_spec, dict):
        fail("SCHEMA_FAIL")

    return {
        "dataset_name": dataset_name,
        "inputs_relpaths": inputs_relpaths,
        "input_content_ids": pins,
        "sip_profile": sip_profile,
        "sip_budget_spec": sip_budget_spec,
    }


def _load_input_entries(*, repo_root_path: Path, inputs_relpaths: list[str], pinned_ids: dict[str, str]) -> tuple[list[dict[str, Any]], list[str]]:
    entries: list[dict[str, Any]] = []
    mismatches: list[str] = []
    for relpath in inputs_relpaths:
        abs_path = (repo_root_path / relpath).resolve()
        blob: bytes | None = None
        actual_id = _ZERO_SHA256
        if abs_path.exists() and abs_path.is_file():
            blob = abs_path.read_bytes()
            actual_id = _sha256_bytes(blob)
        else:
            mismatches.append(f"MISSING_INPUT:{relpath}")

        expected_id = pinned_ids[relpath]
        if blob is not None and actual_id != expected_id:
            mismatches.append(f"PIN_MISMATCH:{relpath}:expected={expected_id}:actual={actual_id}")

        entries.append(
            {
                "relpath": relpath,
                "blob": blob,
                "actual_id": actual_id,
                "expected_id": expected_id,
            }
        )
    return entries, sorted(mismatches)


def _frame_raw_bytes(entries: list[dict[str, Any]]) -> bytes:
    framed = bytearray()
    for row in entries:
        relpath = str(row["relpath"])
        rel_raw = relpath.encode("utf-8")
        blob = row.get("blob")
        exists = isinstance(blob, (bytes, bytearray))
        blob_bytes = bytes(blob) if exists else b""

        framed.extend(len(rel_raw).to_bytes(8, "big", signed=False))
        framed.extend(rel_raw)
        framed.extend((1 if exists else 0).to_bytes(1, "big", signed=False))
        framed.extend(len(blob_bytes).to_bytes(8, "big", signed=False))
        framed.extend(blob_bytes)
    return bytes(framed)


def canonicalize_jsonl_bytes_from_inputs(*, input_bytes_by_relpath: dict[str, bytes]) -> tuple[bytes, int]:
    if not isinstance(input_bytes_by_relpath, dict):
        fail("SCHEMA_FAIL")

    canonical_rows: list[bytes] = []
    for relpath in sorted(input_bytes_by_relpath.keys()):
        require_relpath(relpath)
        blob = input_bytes_by_relpath[relpath]
        if not isinstance(blob, (bytes, bytearray)):
            fail("SCHEMA_FAIL")

        try:
            text = bytes(blob).decode("utf-8")
        except UnicodeDecodeError:
            fail("CANON_JSONL_PARSE_FAIL")

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                parsed = loads(line)
            except Exception:  # noqa: BLE001
                fail("CANON_JSONL_PARSE_FAIL")
            try:
                canonical_rows.append(canon_bytes(parsed))
            except Exception:  # noqa: BLE001
                fail("CANON_JSONL_PARSE_FAIL")

    canonical_rows.sort(key=lambda row: (hashlib.sha256(row).digest(), row))
    if not canonical_rows:
        return b"", 0
    return b"\n".join(canonical_rows) + b"\n", int(len(canonical_rows))


def _write_blob(*, blobs_root: Path, content_id: str, blob: bytes) -> Path:
    digest = _ensure_sha256(content_id).split(":", 1)[1]
    path = blobs_root / digest
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if hash_file_stream(path) != content_id:
            fail("NONDETERMINISTIC")
        if path.read_bytes() != blob:
            fail("NONDETERMINISTIC")
        return path
    path.write_bytes(blob)
    if hash_file_stream(path) != content_id:
        fail("NONDETERMINISTIC")
    return path


def _manifest_entry(*, logical_path: str, content_id: str, blob: bytes) -> dict[str, Any]:
    return {
        "logical_path": logical_path,
        "content_id": content_id,
        "content_length_bytes": int(len(blob)),
        "content_kind": "RAW_BYTES",
        "canon_version": None,
        "content_artifact_ref": {
            "schema_name": "blob_artifact_v1",
            "schema_version": "v19_0",
            "id": content_id,
        },
    }


def _build_manifest(*, dataset_name: str, raw_bytes_content_id: str, raw_bytes: bytes, canonical_jsonl_content_id: str, canonical_jsonl_bytes: bytes) -> dict[str, Any]:
    entries = [
        _manifest_entry(
            logical_path=f"datasets/{dataset_name}/canonical.jsonl",
            content_id=canonical_jsonl_content_id,
            blob=canonical_jsonl_bytes,
        ),
        _manifest_entry(
            logical_path=f"datasets/{dataset_name}/raw_input_frame.bin",
            content_id=raw_bytes_content_id,
            blob=raw_bytes,
        ),
    ]
    entries.sort(key=lambda row: str(row["logical_path"]))
    manifest = {
        "schema_name": "world_snapshot_manifest_v1",
        "schema_version": "v19_0",
        "path_normalization": "NFC_FORWARD_SLASH",
        "ordering_rule": "UNICODE_CODEPOINT_THEN_UTF8_BYTES",
        "entries": entries,
    }
    manifest["manifest_id"] = canon_hash_obj(manifest)
    return manifest


def _build_world_snapshot_id(*, dataset_name: str, tick_u64: int, raw_bytes_content_id: str, canonical_jsonl_content_id: str, manifest_id: str) -> str:
    payload = {
        "schema_version": "sip_world_snapshot_seed_v1",
        "dataset_name": dataset_name,
        "tick_u64": int(tick_u64),
        "raw_bytes_content_id": raw_bytes_content_id,
        "canonical_jsonl_content_id": canonical_jsonl_content_id,
        "manifest_id": manifest_id,
    }
    return canon_hash_obj(payload)


def _build_world_task_binding(*, dataset_name: str, world_snapshot_id: str, manifest_id: str, raw_bytes_content_id: str, canonical_jsonl_content_id: str) -> dict[str, Any]:
    payload = {
        "schema_name": "world_task_binding_v1",
        "schema_version": "v19_0",
        "task_id": f"sip_ingestion_l0::{dataset_name}",
        "world_snapshot_id": world_snapshot_id,
        "manifest_ref": manifest_id,
        "data_dependency_content_ids": sorted([raw_bytes_content_id, canonical_jsonl_content_id]),
        "evaluation_input_content_ids": [canonical_jsonl_content_id],
        "forbids_external_dependencies": True,
    }
    payload["binding_id"] = canon_hash_obj(payload)
    return payload


def compute_producer_run_id(*, dataset_name: str, tick_u64: int, raw_bytes_content_id: str, canonical_jsonl_content_id: str | None) -> str:
    payload = {
        "schema_version": "sip_ingestion_l0_producer_run_id_v1",
        "dataset_name": dataset_name,
        "tick_u64": int(tick_u64),
        "raw_bytes_content_id": raw_bytes_content_id,
        "canonical_jsonl_content_id": canonical_jsonl_content_id or _ZERO_SHA256,
    }
    return canon_hash_obj(payload)


def _write_refutation(
    *,
    refutations_dir: Path,
    dataset_name: str,
    reason_code: str,
    producer_run_id: str,
    tick_u64: int,
    inputs_relpaths: list[str],
    input_content_ids: dict[str, str],
    raw_bytes_content_id: str,
    canonical_jsonl_content_id: str | None,
    sip_manifest_id: str | None,
    sip_seal_receipt_id: str | None,
    detail: str | None,
) -> tuple[Path, dict[str, Any], str]:
    payload: dict[str, Any] = {
        "schema_version": "sip_knowledge_refutation_v1",
        "dataset_name": dataset_name,
        "reason_code": reason_code,
        "producer_run_id": producer_run_id,
        "tick_u64": int(tick_u64),
        "inputs_relpaths": list(inputs_relpaths),
        "input_content_ids": dict(input_content_ids),
        "raw_bytes_content_id": raw_bytes_content_id,
        "canonical_jsonl_content_id": canonical_jsonl_content_id,
        "sip_manifest_id": sip_manifest_id,
        "sip_seal_receipt_id": sip_seal_receipt_id,
    }
    if detail:
        payload["detail"] = str(detail)
    validate_schema(payload, "sip_knowledge_refutation_v1")
    return write_hashed_json(refutations_dir, "sip_knowledge_refutation_v1.json", payload)


def run_sip_ingestion_l0(
    *,
    config: dict[str, Any],
    repo_root_path: Path,
    state_root: Path,
    tick_u64: int,
) -> dict[str, Any]:
    normalized = _normalize_pack(config)
    dataset_name = str(normalized["dataset_name"])
    inputs_relpaths = list(normalized["inputs_relpaths"])
    input_content_ids = dict(normalized["input_content_ids"])
    sip_profile = dict(normalized["sip_profile"])
    sip_budget_spec = dict(normalized["sip_budget_spec"])

    ingestion_root = state_root.resolve() / "polymath" / "ingestion"
    blobs_root = ingestion_root / "blobs" / "sha256"
    manifests_dir = ingestion_root / "manifests"
    receipts_dir = ingestion_root / "receipts"
    knowledge_dir = ingestion_root / "knowledge"
    refutations_dir = ingestion_root / "refutations"
    for path in (blobs_root, manifests_dir, receipts_dir, knowledge_dir, refutations_dir):
        path.mkdir(parents=True, exist_ok=True)

    input_entries, mismatches = _load_input_entries(
        repo_root_path=repo_root_path.resolve(),
        inputs_relpaths=inputs_relpaths,
        pinned_ids=input_content_ids,
    )
    raw_bytes = _frame_raw_bytes(input_entries)
    raw_bytes_content_id = _sha256_bytes(raw_bytes)
    _write_blob(blobs_root=blobs_root, content_id=raw_bytes_content_id, blob=raw_bytes)

    canonical_jsonl_content_id: str | None = None
    canonical_jsonl_bytes = b""
    record_count_u64 = 0
    parse_refutation_detail: str | None = None

    if not mismatches:
        canonical_input_blobs = {
            str(row["relpath"]): bytes(row["blob"])
            for row in input_entries
            if isinstance(row.get("blob"), (bytes, bytearray))
        }
        try:
            canonical_jsonl_bytes, record_count_u64 = canonicalize_jsonl_bytes_from_inputs(
                input_bytes_by_relpath=canonical_input_blobs
            )
        except OmegaV18Error as exc:
            msg = str(exc)
            if "CANON_JSONL_PARSE_FAIL" not in msg:
                raise
            parse_refutation_detail = msg
        else:
            canonical_jsonl_content_id = _sha256_bytes(canonical_jsonl_bytes)
            _write_blob(
                blobs_root=blobs_root,
                content_id=canonical_jsonl_content_id,
                blob=canonical_jsonl_bytes,
            )

    producer_run_id = compute_producer_run_id(
        dataset_name=dataset_name,
        tick_u64=tick_u64,
        raw_bytes_content_id=raw_bytes_content_id,
        canonical_jsonl_content_id=canonical_jsonl_content_id,
    )

    subrun_root = _subrun_root_from_state(state_root.resolve())

    if mismatches:
        ref_path, _ref_obj, ref_hash = _write_refutation(
            refutations_dir=refutations_dir,
            dataset_name=dataset_name,
            reason_code="INPUT_HASH_MISMATCH",
            producer_run_id=producer_run_id,
            tick_u64=tick_u64,
            inputs_relpaths=inputs_relpaths,
            input_content_ids=input_content_ids,
            raw_bytes_content_id=raw_bytes_content_id,
            canonical_jsonl_content_id=canonical_jsonl_content_id,
            sip_manifest_id=None,
            sip_seal_receipt_id=None,
            detail=";".join(mismatches),
        )
        return {
            "status": "REFUTED",
            "reason_code": "INPUT_HASH_MISMATCH",
            "producer_run_id": producer_run_id,
            "dataset_name": dataset_name,
            "knowledge_artifact_hash": None,
            "knowledge_artifact_rel": None,
            "refutation_hash": ref_hash,
            "refutation_rel": _relpath_from_subrun(subrun_root=subrun_root, path=ref_path),
            "manifest_hash": None,
            "manifest_rel": None,
            "receipt_hash": None,
            "receipt_rel": None,
        }

    if parse_refutation_detail is not None:
        ref_path, _ref_obj, ref_hash = _write_refutation(
            refutations_dir=refutations_dir,
            dataset_name=dataset_name,
            reason_code="CANON_JSONL_PARSE_FAIL",
            producer_run_id=producer_run_id,
            tick_u64=tick_u64,
            inputs_relpaths=inputs_relpaths,
            input_content_ids=input_content_ids,
            raw_bytes_content_id=raw_bytes_content_id,
            canonical_jsonl_content_id=canonical_jsonl_content_id,
            sip_manifest_id=None,
            sip_seal_receipt_id=None,
            detail=parse_refutation_detail,
        )
        return {
            "status": "REFUTED",
            "reason_code": "CANON_JSONL_PARSE_FAIL",
            "producer_run_id": producer_run_id,
            "dataset_name": dataset_name,
            "knowledge_artifact_hash": None,
            "knowledge_artifact_rel": None,
            "refutation_hash": ref_hash,
            "refutation_rel": _relpath_from_subrun(subrun_root=subrun_root, path=ref_path),
            "manifest_hash": None,
            "manifest_rel": None,
            "receipt_hash": None,
            "receipt_rel": None,
        }

    if canonical_jsonl_content_id is None:
        fail("SCHEMA_FAIL")

    manifest = _build_manifest(
        dataset_name=dataset_name,
        raw_bytes_content_id=raw_bytes_content_id,
        raw_bytes=raw_bytes,
        canonical_jsonl_content_id=canonical_jsonl_content_id,
        canonical_jsonl_bytes=canonical_jsonl_bytes,
    )
    world_snapshot_id = _build_world_snapshot_id(
        dataset_name=dataset_name,
        tick_u64=tick_u64,
        raw_bytes_content_id=raw_bytes_content_id,
        canonical_jsonl_content_id=canonical_jsonl_content_id,
        manifest_id=str(manifest["manifest_id"]),
    )
    world_task_binding = _build_world_task_binding(
        dataset_name=dataset_name,
        world_snapshot_id=world_snapshot_id,
        manifest_id=str(manifest["manifest_id"]),
        raw_bytes_content_id=raw_bytes_content_id,
        canonical_jsonl_content_id=canonical_jsonl_content_id,
    )

    manifest_path, manifest_obj, manifest_hash = write_hashed_json(
        manifests_dir,
        "world_snapshot_manifest_v1.json",
        manifest,
        id_field="manifest_id",
    )
    if str(manifest_obj.get("manifest_id", "")) != canon_hash_obj(
        {k: v for k, v in manifest_obj.items() if k != "manifest_id"}
    ):
        fail("NONDETERMINISTIC")

    receipt = run_sip(
        manifest=manifest_obj,
        artifact_bytes_by_content_id={
            raw_bytes_content_id: raw_bytes,
            canonical_jsonl_content_id: canonical_jsonl_bytes,
        },
        sip_profile=sip_profile,
        world_task_bindings=[world_task_binding],
        world_snapshot_id=world_snapshot_id,
        budget_spec=sip_budget_spec,
    )

    receipt_path, receipt_obj, receipt_hash = write_hashed_json(
        receipts_dir,
        "sealed_ingestion_receipt_v1.json",
        receipt,
    )

    receipt_outcome = str(receipt_obj.get("outcome", "")).strip()
    receipt_reason_code = str(receipt_obj.get("reason_code", "")).strip()

    if receipt_outcome == "ACCEPT" and receipt_reason_code == "GATES_PASS":
        leakage_gate = (receipt_obj.get("gate_results") or {}).get("leakage_gate")
        leakage_passed_b = (
            isinstance(leakage_gate, dict)
            and str(leakage_gate.get("outcome", "")).strip() == "ACCEPT"
            and not bool(leakage_gate.get("flags", []))
        )
        payload = {
            "schema_version": "sip_knowledge_artifact_v1",
            "dataset_name": dataset_name,
            "raw_bytes_content_id": raw_bytes_content_id,
            "canonical_jsonl_content_id": canonical_jsonl_content_id,
            "sip_manifest_id": str(manifest_obj.get("manifest_id")),
            "sip_seal_receipt_id": str(receipt_obj.get("receipt_id")),
            "entropy_q16": int(_entropy_q16(canonical_jsonl_bytes)),
            "leakage_scan_passed_b": bool(leakage_passed_b),
            "record_count_u64": int(record_count_u64),
            "bytes_u64": int(len(canonical_jsonl_bytes)),
            "producer_run_id": producer_run_id,
            "tick_u64": int(tick_u64),
            "inputs_relpaths": list(inputs_relpaths),
            "input_content_ids": dict(input_content_ids),
        }
        validate_schema(payload, "sip_knowledge_artifact_v1")
        knowledge_path, _knowledge_obj, knowledge_hash = write_hashed_json(
            knowledge_dir,
            "sip_knowledge_artifact_v1.json",
            payload,
        )
        return {
            "status": "SUCCESS",
            "reason_code": None,
            "producer_run_id": producer_run_id,
            "dataset_name": dataset_name,
            "knowledge_artifact_hash": knowledge_hash,
            "knowledge_artifact_rel": _relpath_from_subrun(subrun_root=subrun_root, path=knowledge_path),
            "refutation_hash": None,
            "refutation_rel": None,
            "manifest_hash": manifest_hash,
            "manifest_rel": _relpath_from_subrun(subrun_root=subrun_root, path=manifest_path),
            "receipt_hash": receipt_hash,
            "receipt_rel": _relpath_from_subrun(subrun_root=subrun_root, path=receipt_path),
        }

    if receipt_reason_code == "BUDGET_EXHAUSTED":
        ref_reason = "BUDGET_EXHAUSTED"
    elif receipt_outcome == "REJECT":
        ref_reason = "SIP_REJECTED"
    else:
        ref_reason = "SIP_SAFE_HALT"

    ref_path, _ref_obj, ref_hash = _write_refutation(
        refutations_dir=refutations_dir,
        dataset_name=dataset_name,
        reason_code=ref_reason,
        producer_run_id=producer_run_id,
        tick_u64=tick_u64,
        inputs_relpaths=inputs_relpaths,
        input_content_ids=input_content_ids,
        raw_bytes_content_id=raw_bytes_content_id,
        canonical_jsonl_content_id=canonical_jsonl_content_id,
        sip_manifest_id=str(manifest_obj.get("manifest_id")),
        sip_seal_receipt_id=str(receipt_obj.get("receipt_id")),
        detail=f"outcome={receipt_outcome};reason={receipt_reason_code}",
    )
    return {
        "status": "REFUTED",
        "reason_code": ref_reason,
        "producer_run_id": producer_run_id,
        "dataset_name": dataset_name,
        "knowledge_artifact_hash": None,
        "knowledge_artifact_rel": None,
        "refutation_hash": ref_hash,
        "refutation_rel": _relpath_from_subrun(subrun_root=subrun_root, path=ref_path),
        "manifest_hash": manifest_hash,
        "manifest_rel": _relpath_from_subrun(subrun_root=subrun_root, path=manifest_path),
        "receipt_hash": receipt_hash,
        "receipt_rel": _relpath_from_subrun(subrun_root=subrun_root, path=receipt_path),
    }


__all__ = [
    "canonicalize_jsonl_bytes_from_inputs",
    "compute_producer_run_id",
    "run_sip_ingestion_l0",
]
