"""Deterministic non-destructive compaction verification helpers."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

from ..common_v1 import canon_hash_obj, ensure_sha256, fail, validate_schema, verify_object_id

_SHA_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _ordered_hash(*, schema_version: str, values: list[str]) -> str:
    ordered = sorted(ensure_sha256(v, reason="SCHEMA_FAIL") for v in values)
    return canon_hash_obj({"schema_version": schema_version, "values": ordered})


def _find_artifact_file_by_hash(*, state_root: Path, artifact_hash: str) -> Path | None:
    digest = ensure_sha256(artifact_hash, reason="SCHEMA_FAIL").split(":", 1)[1]
    matches = sorted(state_root.rglob(f"sha256_{digest}.*.json"), key=lambda p: p.as_posix())
    if not matches:
        return None
    return matches[0]


def _iter_sha_refs(node: Any) -> list[str]:
    out: list[str] = []
    stack = [node]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for value in cur.values():
                stack.append(value)
            continue
        if isinstance(cur, list):
            stack.extend(cur)
            continue
        if isinstance(cur, str):
            value = cur.strip()
            if _SHA_RE.fullmatch(value):
                out.append(value)
    return out


def _validate_ledger_event_v1(row: dict[str, Any]) -> None:
    # Compaction reachability consumes persisted ledger rows that are still v18 schema objects.
    if str(row.get("schema_version", "")).strip() != "omega_ledger_event_v1":
        fail("SCHEMA_FAIL")
    verify_object_id(row, id_field="event_id")
    tick_u64 = row.get("tick_u64")
    if not isinstance(tick_u64, int) or tick_u64 < 0:
        fail("SCHEMA_FAIL")
    event_type = row.get("event_type")
    if not isinstance(event_type, str) or not event_type.strip():
        fail("SCHEMA_FAIL")
    ensure_sha256(row.get("artifact_hash"), reason="SCHEMA_FAIL")
    prev_event_id = row.get("prev_event_id")
    if prev_event_id is not None:
        ensure_sha256(prev_event_id, reason="SCHEMA_FAIL")


def compute_reachable_artifact_ids_to_floor(*, state_root: Path, replay_floor_tick_u64: int) -> list[str]:
    ledger_dir = state_root / "ledger"
    if not ledger_dir.exists() or not ledger_dir.is_dir():
        fail("MISSING_STATE_INPUT")
    rows = sorted(ledger_dir.glob("sha256_*.omega_ledger_event_v1.json"), key=lambda p: p.as_posix())
    if not rows:
        return []

    frontier: list[str] = []
    seen: set[str] = set()
    for row in rows:
        payload = json.loads(row.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            fail("SCHEMA_FAIL")
        if canon_hash_obj(payload) != "sha256:" + row.name.split(".", 1)[0].split("_", 1)[1]:
            fail("NONDETERMINISTIC")
        _validate_ledger_event_v1(payload)
        if int(payload.get("tick_u64", -1)) > int(replay_floor_tick_u64):
            continue
        artifact_hash = ensure_sha256(payload.get("artifact_hash"), reason="SCHEMA_FAIL")
        if artifact_hash not in seen:
            seen.add(artifact_hash)
            frontier.append(artifact_hash)

    idx = 0
    while idx < len(frontier):
        artifact_hash = frontier[idx]
        idx += 1
        path = _find_artifact_file_by_hash(state_root=state_root, artifact_hash=artifact_hash)
        if path is None:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            fail("SCHEMA_FAIL")
        refs = _iter_sha_refs(payload)
        for ref in sorted(set(refs)):
            if ref in seen:
                continue
            seen.add(ref)
            frontier.append(ref)
    return sorted(seen)


def verify_compaction_bundle(
    *,
    state_root: Path,
    execution_receipt: dict[str, Any],
    witness: dict[str, Any],
    pack_manifest: dict[str, Any],
    mapping_manifest: dict[str, Any],
    tombstone_manifest: dict[str, Any],
) -> dict[str, Any]:
    validate_schema(execution_receipt, "epistemic_compaction_execution_receipt_v1")
    validate_schema(witness, "epistemic_compaction_witness_v1")
    validate_schema(pack_manifest, "epistemic_compaction_pack_manifest_v1")
    validate_schema(mapping_manifest, "epistemic_compaction_mapping_manifest_v1")
    validate_schema(tombstone_manifest, "epistemic_compaction_tombstone_manifest_v1")

    receipt_id = verify_object_id(execution_receipt, id_field="receipt_id")
    witness_id = verify_object_id(witness, id_field="witness_id")
    pack_manifest_id = verify_object_id(pack_manifest, id_field="pack_manifest_id")
    mapping_manifest_id = verify_object_id(mapping_manifest, id_field="mapping_manifest_id")
    tombstone_manifest_id = verify_object_id(tombstone_manifest, id_field="tombstone_manifest_id")

    if ensure_sha256(execution_receipt.get("pack_manifest_id"), reason="SCHEMA_FAIL") != pack_manifest_id:
        fail("NONDETERMINISTIC")
    if ensure_sha256(execution_receipt.get("mapping_manifest_id"), reason="SCHEMA_FAIL") != mapping_manifest_id:
        fail("NONDETERMINISTIC")
    if ensure_sha256(execution_receipt.get("tombstone_manifest_id"), reason="SCHEMA_FAIL") != tombstone_manifest_id:
        fail("NONDETERMINISTIC")

    replay_floor_tick_u64 = int(execution_receipt.get("replay_floor_tick_u64", -1))
    if replay_floor_tick_u64 < 0:
        fail("SCHEMA_FAIL")
    if int(witness.get("replay_floor_tick_u64", -1)) != replay_floor_tick_u64:
        fail("NONDETERMINISTIC")

    tombstoned = sorted(
        ensure_sha256(v, reason="SCHEMA_FAIL") for v in list(tombstone_manifest.get("tombstoned_blob_ids") or [])
    )
    retained_roots = sorted(
        ensure_sha256(v, reason="SCHEMA_FAIL")
        for v in [
            execution_receipt.get("pre_store_root_id"),
            execution_receipt.get("post_store_root_id"),
            execution_receipt.get("pack_manifest_id"),
            execution_receipt.get("mapping_manifest_id"),
            execution_receipt.get("tombstone_manifest_id"),
        ]
    )
    if _ordered_hash(schema_version="epistemic_compaction_candidate_set_v1", values=tombstoned) != str(
        witness.get("candidate_set_ordered_hash", "")
    ):
        fail("NONDETERMINISTIC")
    if _ordered_hash(schema_version="epistemic_compaction_retained_roots_v1", values=retained_roots) != str(
        witness.get("retained_root_set_ordered_hash", "")
    ):
        fail("NONDETERMINISTIC")

    reachable = compute_reachable_artifact_ids_to_floor(
        state_root=state_root,
        replay_floor_tick_u64=replay_floor_tick_u64,
    )
    reachable_hash = _ordered_hash(
        schema_version="epistemic_compaction_reachable_to_floor_v1",
        values=reachable,
    )
    if reachable_hash != str(witness.get("reachable_from_any_tick_0_to_floor_ordered_hash", "")):
        fail("NONDETERMINISTIC")

    reachable_set = set(reachable)
    mapping_rows_raw = mapping_manifest.get("rows")
    if not isinstance(mapping_rows_raw, list):
        fail("SCHEMA_FAIL")
    mapping_rows: dict[str, dict[str, Any]] = {}
    for row in mapping_rows_raw:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        old_blob_id = ensure_sha256(row.get("old_blob_id"), reason="SCHEMA_FAIL")
        mapping_rows[old_blob_id] = dict(row)

    pack_blob_set = set(ensure_sha256(v, reason="SCHEMA_FAIL") for v in list(pack_manifest.get("blob_ids") or []))
    for blob_id in tombstoned:
        if blob_id in reachable_set:
            fail("NONDETERMINISTIC")
        mapping_row = mapping_rows.get(blob_id)
        if mapping_row is None:
            fail("MISSING_STATE_INPUT")
        present_in_pack_b = bool(mapping_row.get("present_in_pack_b", False))
        if not present_in_pack_b:
            fail("NONDETERMINISTIC")
        if blob_id not in pack_blob_set:
            fail("NONDETERMINISTIC")

    return {
        "receipt_id": receipt_id,
        "witness_id": witness_id,
        "replay_floor_tick_u64": int(replay_floor_tick_u64),
        "reachable_count_u64": int(len(reachable)),
        "tombstoned_count_u64": int(len(tombstoned)),
    }


def _write_hashed_json(*, out_dir: Path, suffix: str, payload: dict[str, Any], id_field: str) -> tuple[dict[str, Any], str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    materialized = dict(payload)
    no_id = dict(materialized)
    no_id.pop(id_field, None)
    materialized[id_field] = canon_hash_obj(no_id)
    digest = ensure_sha256(materialized.get(id_field), reason="SCHEMA_FAIL")
    path = out_dir / f"sha256_{digest.split(':', 1)[1]}.{suffix}"
    path.write_text(json.dumps(materialized, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
    # Object IDs are canon hashes over the payload with ID field removed.
    observed_no_id = dict(materialized)
    observed_no_id.pop(id_field, None)
    if canon_hash_obj(observed_no_id) != digest:
        fail("NONDETERMINISTIC")
    return materialized, digest


def _iter_hot_blob_ids(hot_sha_dir: Path) -> list[str]:
    out: list[str] = []
    if not hot_sha_dir.exists() or not hot_sha_dir.is_dir():
        return []
    for path in sorted(hot_sha_dir.glob("*"), key=lambda p: p.as_posix()):
        if not path.is_file():
            continue
        digest = path.name.strip()
        if len(digest) != 64:
            fail("SCHEMA_FAIL")
        blob = path.read_bytes()
        blob_id = "sha256:" + digest
        if "sha256:" + hashlib.sha256(blob).hexdigest() != blob_id:
            fail("HASH_MISMATCH")
        out.append(blob_id)
    return sorted(out)


def _seed_hot_store_if_empty(*, state_root: Path, hot_sha_dir: Path) -> None:
    hot_sha_dir.mkdir(parents=True, exist_ok=True)
    if any(True for _ in hot_sha_dir.glob("*")):
        return
    src_dir = state_root / "epistemic" / "replay_inputs" / "mob_blobs" / "sha256"
    if not src_dir.exists() or not src_dir.is_dir():
        return
    for src in sorted(src_dir.glob("*"), key=lambda p: p.as_posix()):
        if not src.is_file():
            continue
        dst = hot_sha_dir / src.name
        if dst.exists():
            continue
        shutil.copy2(src, dst)


def execute_compaction_campaign(
    *,
    state_root: Path,
    replay_floor_tick_u64: int,
) -> dict[str, Any]:
    replay_floor_tick_u64 = int(replay_floor_tick_u64)
    if replay_floor_tick_u64 < 0:
        fail("SCHEMA_FAIL")
    retention_root = state_root / "epistemic" / "retention"
    hot_sha_dir = state_root / "epistemic" / "blob_store" / "hot" / "sha256"
    cold_root = state_root / "epistemic" / "blob_store" / "cold"
    _seed_hot_store_if_empty(state_root=state_root, hot_sha_dir=hot_sha_dir)
    candidate_blob_ids = _iter_hot_blob_ids(hot_sha_dir)
    reachable_to_floor = compute_reachable_artifact_ids_to_floor(
        state_root=state_root,
        replay_floor_tick_u64=replay_floor_tick_u64,
    )
    reachable_set = set(reachable_to_floor)
    tombstoned_blob_ids = sorted(blob_id for blob_id in candidate_blob_ids if blob_id not in reachable_set)
    pre_store_root_id = _ordered_hash(
        schema_version="epistemic_compaction_hot_store_root_v1",
        values=candidate_blob_ids,
    )

    pack_manifest_base = {
        "schema_version": "epistemic_compaction_pack_manifest_v1",
        "pack_manifest_id": "sha256:" + ("0" * 64),
        "store_root_id": pre_store_root_id,
        "blob_ids": list(tombstoned_blob_ids),
    }
    pack_manifest, pack_manifest_id = _write_hashed_json(
        out_dir=retention_root,
        suffix="epistemic_compaction_pack_manifest_v1.json",
        payload=pack_manifest_base,
        id_field="pack_manifest_id",
    )
    pack_dir = cold_root / f"pack_{pack_manifest_id.split(':', 1)[1]}" / "sha256"
    pack_dir.mkdir(parents=True, exist_ok=True)

    mapping_rows: list[dict[str, Any]] = []
    for blob_id in tombstoned_blob_ids:
        digest = blob_id.split(":", 1)[1]
        hot_path = hot_sha_dir / digest
        if not hot_path.exists() or not hot_path.is_file():
            fail("MISSING_STATE_INPUT")
        cold_path = pack_dir / digest
        shutil.copy2(hot_path, cold_path)
        blob = cold_path.read_bytes()
        if "sha256:" + hashlib.sha256(blob).hexdigest() != blob_id:
            fail("HASH_MISMATCH")
        hot_path.unlink()
        mapping_rows.append(
            {
                "old_blob_id": blob_id,
                "present_in_pack_b": True,
                "new_location_ref": f"cold://{pack_manifest_id.split(':', 1)[1]}/{digest}",
            }
        )
    mapping_rows.sort(key=lambda row: str(row.get("old_blob_id", "")))
    mapping_manifest_base = {
        "schema_version": "epistemic_compaction_mapping_manifest_v1",
        "mapping_manifest_id": "sha256:" + ("0" * 64),
        "rows": mapping_rows,
    }
    mapping_manifest, mapping_manifest_id = _write_hashed_json(
        out_dir=retention_root,
        suffix="epistemic_compaction_mapping_manifest_v1.json",
        payload=mapping_manifest_base,
        id_field="mapping_manifest_id",
    )
    tombstone_manifest_base = {
        "schema_version": "epistemic_compaction_tombstone_manifest_v1",
        "tombstone_manifest_id": "sha256:" + ("0" * 64),
        "tombstoned_blob_ids": list(tombstoned_blob_ids),
    }
    tombstone_manifest, tombstone_manifest_id = _write_hashed_json(
        out_dir=retention_root,
        suffix="epistemic_compaction_tombstone_manifest_v1.json",
        payload=tombstone_manifest_base,
        id_field="tombstone_manifest_id",
    )
    remaining_hot_blob_ids = _iter_hot_blob_ids(hot_sha_dir)
    post_store_root_id = _ordered_hash(
        schema_version="epistemic_compaction_hot_store_root_v1",
        values=remaining_hot_blob_ids,
    )
    execution_receipt_base = {
        "schema_version": "epistemic_compaction_execution_receipt_v1",
        "receipt_id": "sha256:" + ("0" * 64),
        "replay_floor_tick_u64": int(replay_floor_tick_u64),
        "pre_store_root_id": pre_store_root_id,
        "post_store_root_id": post_store_root_id,
        "pack_manifest_id": pack_manifest_id,
        "mapping_manifest_id": mapping_manifest_id,
        "tombstone_manifest_id": tombstone_manifest_id,
    }
    execution_receipt, execution_receipt_id = _write_hashed_json(
        out_dir=retention_root,
        suffix="epistemic_compaction_execution_receipt_v1.json",
        payload=execution_receipt_base,
        id_field="receipt_id",
    )
    witness_base = {
        "schema_version": "epistemic_compaction_witness_v1",
        "witness_id": "sha256:" + ("0" * 64),
        "replay_floor_tick_u64": int(replay_floor_tick_u64),
        "candidate_set_ordered_hash": _ordered_hash(
            schema_version="epistemic_compaction_candidate_set_v1",
            values=tombstoned_blob_ids,
        ),
        "retained_root_set_ordered_hash": _ordered_hash(
            schema_version="epistemic_compaction_retained_roots_v1",
            values=[
                pre_store_root_id,
                post_store_root_id,
                pack_manifest_id,
                mapping_manifest_id,
                tombstone_manifest_id,
            ],
        ),
        "reachable_from_any_tick_0_to_floor_ordered_hash": _ordered_hash(
            schema_version="epistemic_compaction_reachable_to_floor_v1",
            values=reachable_to_floor,
        ),
        "store_root_being_compacted": pre_store_root_id,
    }
    witness, witness_id = _write_hashed_json(
        out_dir=retention_root,
        suffix="epistemic_compaction_witness_v1.json",
        payload=witness_base,
        id_field="witness_id",
    )
    _ = verify_compaction_bundle(
        state_root=state_root,
        execution_receipt=execution_receipt,
        witness=witness,
        pack_manifest=pack_manifest,
        mapping_manifest=mapping_manifest,
        tombstone_manifest=tombstone_manifest,
    )
    return {
        "execution_receipt": execution_receipt,
        "witness": witness,
        "pack_manifest": pack_manifest,
        "mapping_manifest": mapping_manifest,
        "tombstone_manifest": tombstone_manifest,
        "execution_receipt_id": execution_receipt_id,
        "witness_id": witness_id,
    }


__all__ = [
    "compute_reachable_artifact_ids_to_floor",
    "execute_compaction_campaign",
    "verify_compaction_bundle",
]
