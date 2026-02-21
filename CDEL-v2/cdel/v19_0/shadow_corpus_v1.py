"""Helpers for pinned shadow corpus entry manifests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .common_v1 import canon_hash_obj, ensure_sha256, fail, validate_schema, verify_object_id


def _load_one(dir_path: Path, suffix: str) -> dict[str, Any]:
    rows = sorted(dir_path.glob(f"sha256_*.{suffix}"), key=lambda p: p.as_posix())
    if len(rows) != 1:
        fail("MISSING_STATE_INPUT")
    payload = json.loads(rows[0].read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        fail("SCHEMA_FAIL")
    if canon_hash_obj(payload) != "sha256:" + rows[0].name.split(".", 1)[0].split("_", 1)[1]:
        fail("NONDETERMINISTIC")
    return payload


def _fallback_contract_id(kind: str) -> str:
    return canon_hash_obj(
        {
            "schema_version": "shadow_corpus_missing_contract_v1",
            "kind": str(kind),
        }
    )


def _canon_sha_list(values: Any, *, allow_empty: bool) -> list[str]:
    if not isinstance(values, list):
        fail("SCHEMA_FAIL")
    out = sorted(ensure_sha256(v, reason="SCHEMA_FAIL") for v in values)
    if not allow_empty and not out:
        fail("SCHEMA_FAIL")
    return out


def _entry_manifest_path(*, descriptor_dir: Path, entry_manifest_id: str) -> Path:
    hexd = ensure_sha256(entry_manifest_id, reason="SCHEMA_FAIL").split(":", 1)[1]
    return descriptor_dir / "entries" / f"sha256_{hexd}.shadow_corpus_entry_manifest_v1.json"


def load_shadow_corpus_entries(
    *,
    corpus_descriptor: dict[str, Any],
    descriptor_dir: Path,
) -> dict[str, Any]:
    descriptor_dir = descriptor_dir.resolve()
    validate_schema(corpus_descriptor, "corpus_descriptor_v1")
    descriptor_id = verify_object_id(corpus_descriptor, id_field="descriptor_id")
    entries_raw = corpus_descriptor.get("entries")
    if not isinstance(entries_raw, list) or not entries_raw:
        fail("SCHEMA_FAIL")

    normalized_entries: list[dict[str, Any]] = []
    for row in entries_raw:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        run_id = str(row.get("run_id", "")).strip()
        tick_u64 = int(row.get("tick_u64", -1))
        if not run_id or tick_u64 < 0:
            fail("SCHEMA_FAIL")
        normalized_entries.append(
            {
                "run_id": run_id,
                "tick_u64": int(tick_u64),
                "tick_snapshot_hash": ensure_sha256(row.get("tick_snapshot_hash"), reason="SCHEMA_FAIL"),
                "entry_manifest_id": ensure_sha256(row.get("entry_manifest_id"), reason="SCHEMA_FAIL"),
            }
        )
    normalized_entries.sort(key=lambda row: str(row.get("entry_manifest_id", "")))
    seen_ids: set[str] = set()
    entry_manifests_by_id: dict[str, dict[str, Any]] = {}
    replay_entries: list[dict[str, Any]] = []
    for row in normalized_entries:
        entry_manifest_id = str(row["entry_manifest_id"])
        if entry_manifest_id in seen_ids:
            fail("NONDETERMINISTIC")
        seen_ids.add(entry_manifest_id)
        path = _entry_manifest_path(descriptor_dir=descriptor_dir, entry_manifest_id=entry_manifest_id)
        if not path.exists() or not path.is_file():
            fail("MISSING_STATE_INPUT")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            fail("SCHEMA_FAIL")
        validate_schema(payload, "shadow_corpus_entry_manifest_v1")
        observed_id = verify_object_id(payload, id_field="entry_manifest_id")
        if observed_id != entry_manifest_id:
            fail("NONDETERMINISTIC")
        if str(payload.get("run_id", "")) != str(row["run_id"]):
            fail("NONDETERMINISTIC")
        if int(payload.get("tick_u64", -1)) != int(row["tick_u64"]):
            fail("NONDETERMINISTIC")
        if ensure_sha256(payload.get("tick_snapshot_hash"), reason="SCHEMA_FAIL") != str(row["tick_snapshot_hash"]):
            fail("NONDETERMINISTIC")
        contracts = payload.get("contracts")
        expected_outputs = payload.get("expected_outputs")
        if not isinstance(contracts, dict) or not isinstance(expected_outputs, dict):
            fail("SCHEMA_FAIL")

        replay_entries.append(
            {
                "run_id": str(row["run_id"]),
                "tick_u64": int(row["tick_u64"]),
                "tick_snapshot_hash": str(row["tick_snapshot_hash"]),
                "entry_manifest_id": entry_manifest_id,
                "pinset_id": ensure_sha256(payload.get("pinset_id"), reason="SCHEMA_FAIL"),
                "raw_blob_ids": _canon_sha_list(payload.get("raw_blob_ids"), allow_empty=False),
                "mob_ids": _canon_sha_list(payload.get("mob_ids"), allow_empty=False),
                "mob_receipt_ids": _canon_sha_list(payload.get("mob_receipt_ids"), allow_empty=False),
                "mob_blob_ids": _canon_sha_list(payload.get("mob_blob_ids"), allow_empty=False),
                "contracts": {
                    "chunk_contract_id": ensure_sha256(contracts.get("chunk_contract_id"), reason="SCHEMA_FAIL"),
                    "fetch_contract_id": ensure_sha256(contracts.get("fetch_contract_id"), reason="SCHEMA_FAIL"),
                    "segment_contract_id": ensure_sha256(contracts.get("segment_contract_id"), reason="SCHEMA_FAIL"),
                    "instruction_strip_contract_id": ensure_sha256(
                        contracts.get("instruction_strip_contract_id"),
                        reason="SCHEMA_FAIL",
                    ),
                    "reduce_contract_id": ensure_sha256(contracts.get("reduce_contract_id"), reason="SCHEMA_FAIL"),
                    "cert_profile_id": ensure_sha256(contracts.get("cert_profile_id"), reason="SCHEMA_FAIL"),
                    "type_registry_id": ensure_sha256(contracts.get("type_registry_id"), reason="SCHEMA_FAIL"),
                },
                "expected_outputs": {
                    "capsule_id": ensure_sha256(expected_outputs.get("capsule_id"), reason="SCHEMA_FAIL"),
                    "graph_id": ensure_sha256(expected_outputs.get("graph_id"), reason="SCHEMA_FAIL"),
                    "type_binding_id": ensure_sha256(expected_outputs.get("type_binding_id"), reason="SCHEMA_FAIL"),
                    "ecac_id": ensure_sha256(expected_outputs.get("ecac_id"), reason="SCHEMA_FAIL"),
                    "eufc_id": ensure_sha256(expected_outputs.get("eufc_id"), reason="SCHEMA_FAIL"),
                    "strip_receipt_id": ensure_sha256(expected_outputs.get("strip_receipt_id"), reason="SCHEMA_FAIL"),
                    "cert_profile_id": ensure_sha256(expected_outputs.get("cert_profile_id"), reason="SCHEMA_FAIL"),
                    "task_input_ids": _canon_sha_list(expected_outputs.get("task_input_ids"), allow_empty=True),
                },
            }
        )
        entry_manifests_by_id[entry_manifest_id] = payload
    return {
        "descriptor_id": descriptor_id,
        "corpus_entries": normalized_entries,
        "entry_manifests_by_id": entry_manifests_by_id,
        "replay_entries": replay_entries,
    }


def build_shadow_corpus_entry_manifest_from_state(
    *,
    state_root: Path,
    run_id: str,
    tick_u64: int,
    tick_snapshot_hash: str,
) -> dict[str, Any]:
    state_root = state_root.resolve()
    run_id = str(run_id).strip()
    tick_snapshot_hash = ensure_sha256(tick_snapshot_hash, reason="SCHEMA_FAIL")
    if not run_id:
        fail("SCHEMA_FAIL")
    tick_u64 = int(tick_u64)
    if tick_u64 < 0:
        fail("SCHEMA_FAIL")

    replay_root = state_root / "epistemic" / "replay_inputs"
    episode_manifest = _load_one(replay_root / "episode", "epistemic_episode_outbox_v1.json")
    pinset = _load_one(replay_root / "episode", "epistemic_pinset_v1.json")
    reduce_contract = _load_one(replay_root / "contracts", "epistemic_reduce_contract_v1.json")
    strip_contract = _load_one(replay_root / "contracts", "epistemic_instruction_strip_contract_v1.json")
    type_registry = _load_one(replay_root / "contracts", "epistemic_type_registry_v1.json")
    cert_profile = _load_one(replay_root / "contracts", "epistemic_cert_profile_v1.json")

    capsule = _load_one(state_root / "epistemic" / "capsules", "epistemic_capsule_v1.json")
    graph = _load_one(state_root / "epistemic" / "graphs", "qxwmr_graph_v1.json")
    type_binding = _load_one(state_root / "epistemic" / "type_bindings", "epistemic_type_binding_v1.json")
    ecac = _load_one(state_root / "epistemic" / "certs", "epistemic_ecac_v1.json")
    eufc = _load_one(state_root / "epistemic" / "certs", "epistemic_eufc_v1.json")

    validate_schema(pinset, "epistemic_pinset_v1")
    validate_schema(episode_manifest, "epistemic_episode_outbox_v1")
    validate_schema(reduce_contract, "epistemic_reduce_contract_v1")
    validate_schema(strip_contract, "epistemic_instruction_strip_contract_v1")
    validate_schema(type_registry, "epistemic_type_registry_v1")
    validate_schema(cert_profile, "epistemic_cert_profile_v1")
    validate_schema(capsule, "epistemic_capsule_v1")
    validate_schema(graph, "qxwmr_graph_v1")
    validate_schema(type_binding, "epistemic_type_binding_v1")
    validate_schema(ecac, "epistemic_ecac_v1")
    validate_schema(eufc, "epistemic_eufc_v1")

    raw_blob_ids = list(pinset.get("ordered_raw_blob_ids") or pinset.get("chunk_blob_ids") or [])
    if not raw_blob_ids:
        fail("SCHEMA_FAIL")
    mob_ids = list(episode_manifest.get("mob_ids") or [])
    if not mob_ids:
        fail("SCHEMA_FAIL")
    mob_receipt_rows = sorted(
        (replay_root / "mob_receipts").glob("sha256_*.epistemic_mob_receipt_v1.json"),
        key=lambda p: p.as_posix(),
    )
    mob_blob_rows = sorted((replay_root / "mob_blobs" / "sha256").glob("*"), key=lambda p: p.as_posix())
    if not mob_receipt_rows or not mob_blob_rows:
        fail("SCHEMA_FAIL")
    mob_receipt_ids = ["sha256:" + p.name.split(".", 1)[0].split("_", 1)[1] for p in mob_receipt_rows]
    mob_blob_ids = [f"sha256:{p.name}" for p in mob_blob_rows if p.is_file()]
    if not mob_blob_ids:
        fail("SCHEMA_FAIL")

    manifest = {
        "schema_name": "shadow_corpus_entry_manifest_v1",
        "schema_version": "v19_0",
        "entry_manifest_id": "sha256:" + ("0" * 64),
        "run_id": run_id,
        "tick_u64": int(tick_u64),
        "tick_snapshot_hash": tick_snapshot_hash,
        "source_kind": "REAL_CAPTURED_EPISODE",
        "synthetic_only_b": False,
        "pinset_id": ensure_sha256(pinset.get("pinset_id"), reason="SCHEMA_FAIL"),
        "raw_blob_ids": sorted(ensure_sha256(v, reason="SCHEMA_FAIL") for v in raw_blob_ids),
        "mob_ids": sorted(ensure_sha256(v, reason="SCHEMA_FAIL") for v in mob_ids),
        "mob_receipt_ids": sorted(ensure_sha256(v, reason="SCHEMA_FAIL") for v in mob_receipt_ids),
        "mob_blob_ids": sorted(ensure_sha256(v, reason="SCHEMA_FAIL") for v in mob_blob_ids),
        "contracts": {
            "chunk_contract_id": ensure_sha256(pinset.get("chunk_contract_id"), reason="SCHEMA_FAIL"),
            "fetch_contract_id": _fallback_contract_id("FETCH_CONTRACT_MISSING"),
            "segment_contract_id": _fallback_contract_id("SEGMENT_CONTRACT_MISSING"),
            "instruction_strip_contract_id": verify_object_id(strip_contract, id_field="contract_id"),
            "reduce_contract_id": verify_object_id(reduce_contract, id_field="contract_id"),
            "cert_profile_id": verify_object_id(cert_profile, id_field="cert_profile_id"),
            "type_registry_id": verify_object_id(type_registry, id_field="registry_id"),
        },
        "expected_outputs": {
            "capsule_id": verify_object_id(capsule, id_field="capsule_id"),
            "graph_id": verify_object_id(graph, id_field="graph_id"),
            "type_binding_id": verify_object_id(type_binding, id_field="binding_id"),
            "ecac_id": verify_object_id(ecac, id_field="ecac_id"),
            "eufc_id": verify_object_id(eufc, id_field="eufc_id"),
            "strip_receipt_id": ensure_sha256(capsule.get("strip_receipt_id"), reason="SCHEMA_FAIL"),
            "cert_profile_id": ensure_sha256(capsule.get("cert_profile_id"), reason="SCHEMA_FAIL"),
            "task_input_ids": sorted(ensure_sha256(v, reason="SCHEMA_FAIL") for v in list(eufc.get("task_input_ids") or [])),
        },
    }
    manifest["entry_manifest_id"] = canon_hash_obj({k: v for k, v in manifest.items() if k != "entry_manifest_id"})
    validate_schema(manifest, "shadow_corpus_entry_manifest_v1")
    verify_object_id(manifest, id_field="entry_manifest_id")
    return manifest


__all__ = [
    "build_shadow_corpus_entry_manifest_from_state",
    "load_shadow_corpus_entries",
]
