"""RE0 outbox episode finalizer with atomic completeness + hash-chained index append."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

try:
    from .common_v1 import (
        append_index_row,
        atomic_write_bytes,
        atomic_write_canon_json,
        canon_hash_obj,
        ensure_sha256,
        file_lock,
        fsync_dir,
        fsync_tree_files,
        hash_bytes,
        load_canon_dict,
    )
except Exception:  # pragma: no cover
    from common_v1 import (
        append_index_row,
        atomic_write_bytes,
        atomic_write_canon_json,
        canon_hash_obj,
        ensure_sha256,
        file_lock,
        fsync_dir,
        fsync_tree_files,
        hash_bytes,
        load_canon_dict,
    )


def _episode_id(raw_blob_ids: list[str], mob_ids: list[str], tick_u64: int) -> str:
    return canon_hash_obj(
        {
            "schema_version": "epistemic_episode_identity_v1",
            "tick_u64": int(tick_u64),
            "raw_blob_ids": list(raw_blob_ids),
            "mob_ids": list(mob_ids),
        }
    )


def _mob_v1_id(payload: dict[str, Any]) -> str:
    mob_id = ensure_sha256(payload.get("mob_id"))
    no_id = dict(payload)
    no_id.pop("mob_id", None)
    if canon_hash_obj(no_id) != mob_id:
        raise RuntimeError("NONDETERMINISTIC")
    if str(payload.get("content_kind", "")) != "CANON_JSON":
        raise RuntimeError("MOB_FORMAT_REJECTED")
    return mob_id


def _mob_v2_id(payload: dict[str, Any]) -> str:
    mob_id = ensure_sha256(payload.get("mob_id"))
    no_id = dict(payload)
    no_id.pop("mob_id", None)
    no_id.pop("mob_receipt_id", None)
    if canon_hash_obj(no_id) != mob_id:
        raise RuntimeError("NONDETERMINISTIC")
    if str(payload.get("content_kind", "")) != "BLOB_REF":
        raise RuntimeError("MOB_FORMAT_REJECTED")
    return mob_id


def _load_mob(path: Path) -> tuple[dict[str, Any], dict[str, Any] | None]:
    payload = load_canon_dict(path)
    schema_version = str(payload.get("schema_version", "")).strip()
    if schema_version == "epistemic_model_output_v1":
        _mob_v1_id(payload)
        return payload, None
    if schema_version != "epistemic_model_output_v2":
        raise RuntimeError("SCHEMA_FAIL")
    mob_id = _mob_v2_id(payload)
    episode_id = ensure_sha256(payload.get("episode_id"))
    mob_receipt_id = ensure_sha256(payload.get("mob_receipt_id"))
    mob_blob_id = ensure_sha256(payload.get("mob_blob_id"))
    receipt_path = path.parent / f"sha256_{mob_receipt_id.split(':', 1)[1]}.epistemic_mob_receipt_v1.json"
    receipt_payload = load_canon_dict(receipt_path)
    if str(receipt_payload.get("schema_version", "")) != "epistemic_mob_receipt_v1":
        raise RuntimeError("SCHEMA_FAIL")
    receipt_no_id = dict(receipt_payload)
    receipt_no_id.pop("mob_receipt_id", None)
    if canon_hash_obj(receipt_no_id) != mob_receipt_id:
        raise RuntimeError("NONDETERMINISTIC")
    if ensure_sha256(receipt_payload.get("mob_id")) != mob_id:
        raise RuntimeError("NONDETERMINISTIC")
    if ensure_sha256(receipt_payload.get("episode_id")) != episode_id:
        raise RuntimeError("NONDETERMINISTIC")
    if ensure_sha256(receipt_payload.get("mob_blob_id")) != mob_blob_id:
        raise RuntimeError("NONDETERMINISTIC")
    return payload, receipt_payload


def _materialize_episode(
    *,
    outbox_root: Path,
    tick_u64: int,
    raw_blob_ids: list[str],
    mob_payloads: list[dict[str, Any]],
    mob_receipts: list[dict[str, Any] | None],
    chunk_contract_id: str | None,
    commit_ready_b: bool,
) -> dict[str, Any]:
    raw_blob_ids = [ensure_sha256(row) for row in raw_blob_ids]
    mob_ids = [ensure_sha256(row.get("mob_id")) for row in mob_payloads]
    episode_id = _episode_id(raw_blob_ids, mob_ids, tick_u64)
    episode_dir = outbox_root / "episodes" / episode_id
    episodes_root = outbox_root / "episodes"
    episodes_root.mkdir(parents=True, exist_ok=True)
    if episode_dir.exists():
        raise RuntimeError("EPISODE_EXISTS")

    tmp_dir = Path(tempfile.mkdtemp(prefix=f"tmp_{episode_id.split(':', 1)[1][:12]}_", dir=str(episodes_root.resolve())))
    try:
        (tmp_dir / "mobs").mkdir(parents=True, exist_ok=True)
        (tmp_dir / "chunks").mkdir(parents=True, exist_ok=True)
        (tmp_dir / "pinset").mkdir(parents=True, exist_ok=True)

        effective_chunk_contract_id = (
            ensure_sha256(chunk_contract_id)
            if chunk_contract_id is not None and str(chunk_contract_id).strip()
            else canon_hash_obj(
                {
                    "schema_version": "epistemic_chunk_contract_v1",
                    "kind": "WEB_HTML_SLICE1",
                    "mode": "RAW_BYTES_ORDERED_V1",
                }
            )
        )

        chunk_receipt_ids: list[str] = []
        for idx, raw_blob_id in enumerate(raw_blob_ids):
            row = {
                "schema_version": "epistemic_raw_chunk_v1",
                "chunk_receipt_id": "sha256:" + ("0" * 64),
                "episode_id": episode_id,
                "chunk_index_u64": int(idx),
                "raw_blob_id": raw_blob_id,
                "chunk_contract_id": effective_chunk_contract_id,
            }
            row["chunk_receipt_id"] = canon_hash_obj({k: v for k, v in row.items() if k != "chunk_receipt_id"})
            chunk_receipt_ids.append(str(row["chunk_receipt_id"]))
            atomic_write_canon_json(
                tmp_dir / "chunks" / f"sha256_{row['chunk_receipt_id'].split(':', 1)[1]}.epistemic_raw_chunk_v1.json",
                row,
            )

        pinset = {
            "schema_version": "epistemic_pinset_v1",
            "pinset_id": "sha256:" + ("0" * 64),
            "episode_id": episode_id,
            "chunk_contract_id": effective_chunk_contract_id,
            "ordered_raw_blob_ids": list(raw_blob_ids),
            "ordered_chunk_receipt_ids": list(chunk_receipt_ids),
        }
        pinset["pinset_id"] = canon_hash_obj({k: v for k, v in pinset.items() if k != "pinset_id"})
        atomic_write_canon_json(
            tmp_dir / "pinset" / f"sha256_{pinset['pinset_id'].split(':', 1)[1]}.epistemic_pinset_v1.json",
            pinset,
        )

        for idx, mob in enumerate(mob_payloads):
            mob_id = str(mob["mob_id"])
            schema_version = str(mob.get("schema_version", "")).strip()
            if schema_version == "epistemic_model_output_v1":
                suffix = "epistemic_model_output_v1.json"
            elif schema_version == "epistemic_model_output_v2":
                suffix = "epistemic_model_output_v2.json"
            else:
                raise RuntimeError("SCHEMA_FAIL")
            atomic_write_canon_json(tmp_dir / "mobs" / f"sha256_{mob_id.split(':', 1)[1]}.{suffix}", mob)
            receipt_payload = mob_receipts[idx]
            if receipt_payload is not None:
                receipt_id = ensure_sha256(receipt_payload.get("mob_receipt_id"))
                atomic_write_canon_json(
                    tmp_dir / "mobs" / f"sha256_{receipt_id.split(':', 1)[1]}.epistemic_mob_receipt_v1.json",
                    receipt_payload,
                )

        manifest = {
            "schema_version": "epistemic_episode_outbox_v1",
            "episode_manifest_id": "sha256:" + ("0" * 64),
            "episode_id": episode_id,
            "tick_u64": int(tick_u64),
            "pinset_id": str(pinset["pinset_id"]),
            "mob_ids": list(mob_ids),
            "raw_chunk_receipt_ids": list(chunk_receipt_ids),
            "commit_ready_b": bool(commit_ready_b),
            "complete_b": True,
            "episode_complete_marker_id": "sha256:" + ("0" * 64),
        }
        marker = {
            "schema_version": "epistemic_episode_complete_marker_v1",
            "marker_id": "sha256:" + ("0" * 64),
            "episode_id": episode_id,
            "episode_manifest_id": "sha256:" + ("0" * 64),
            "complete_b": True,
        }
        manifest["episode_manifest_id"] = canon_hash_obj({k: v for k, v in manifest.items() if k != "episode_manifest_id"})
        marker["episode_manifest_id"] = str(manifest["episode_manifest_id"])
        marker["marker_id"] = canon_hash_obj({k: v for k, v in marker.items() if k != "marker_id"})
        manifest["episode_complete_marker_id"] = str(marker["marker_id"])

        atomic_write_canon_json(
            tmp_dir / f"sha256_{manifest['episode_manifest_id'].split(':', 1)[1]}.epistemic_episode_outbox_v1.json",
            manifest,
        )
        atomic_write_canon_json(
            tmp_dir / f"sha256_{marker['marker_id'].split(':', 1)[1]}.epistemic_episode_complete_marker_v1.json",
            marker,
        )

        fsync_tree_files(tmp_dir)
        fsync_dir(tmp_dir)
        os.replace(tmp_dir, episode_dir)
        fsync_dir(episode_dir.parent)

        index_path = outbox_root / "index" / "epistemic_episode_index_v1.jsonl"
        lock_path = outbox_root / "index" / "epistemic_episode_index_v1.lock"
        with file_lock(lock_path):
            row = append_index_row(
                index_path,
                {
                    "schema_version": "epistemic_episode_index_row_v1",
                    "row_hash": "sha256:" + ("0" * 64),
                    "prev_row_hash": None,
                    "episode_id": episode_id,
                    "tick_u64": int(tick_u64),
                    "pinset_id": str(pinset["pinset_id"]),
                    "mob_ids": list(mob_ids),
                    "commit_ready_b": bool(commit_ready_b),
                    "complete_b": True,
                    "episode_manifest_id": str(manifest["episode_manifest_id"]),
                },
            )

        return {
            "episode_id": episode_id,
            "episode_manifest_id": str(manifest["episode_manifest_id"]),
            "episode_complete_marker_id": str(marker["marker_id"]),
            "pinset_id": str(pinset["pinset_id"]),
            "mob_ids": list(mob_ids),
            "index_row_hash": str(row["row_hash"]),
            "episode_dir": str(episode_dir),
        }
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


def run(
    *,
    outbox_root: Path,
    tick_u64: int,
    raw_blob_ids: list[str],
    mob_paths: list[Path],
    chunk_contract_id: str | None = None,
    commit_ready_b: bool,
) -> dict[str, Any]:
    if not raw_blob_ids:
        raise RuntimeError("SCHEMA_FAIL")
    loaded = [_load_mob(path.resolve()) for path in mob_paths]
    mob_payloads = [row[0] for row in loaded]
    mob_receipts = [row[1] for row in loaded]

    for raw_blob_id in raw_blob_ids:
        digest = ensure_sha256(raw_blob_id).split(":", 1)[1]
        blob_path = outbox_root / "blobs" / "sha256" / digest
        if not blob_path.exists() or not blob_path.is_file():
            raise RuntimeError("MISSING_RAW_BLOB")
        if hash_bytes(blob_path.read_bytes()) != raw_blob_id:
            raise RuntimeError("HASH_MISMATCH")
    for mob in mob_payloads:
        if str(mob.get("schema_version", "")) != "epistemic_model_output_v2":
            continue
        mob_blob_id = ensure_sha256(mob.get("mob_blob_id"))
        digest = mob_blob_id.split(":", 1)[1]
        blob_path = outbox_root / "blobs" / "sha256" / digest
        if not blob_path.exists() or not blob_path.is_file():
            raise RuntimeError("MISSING_MOB_BLOB")
        if hash_bytes(blob_path.read_bytes()) != mob_blob_id:
            raise RuntimeError("HASH_MISMATCH")

    return _materialize_episode(
        outbox_root=outbox_root.resolve(),
        tick_u64=int(tick_u64),
        raw_blob_ids=raw_blob_ids,
        mob_payloads=mob_payloads,
        mob_receipts=mob_receipts,
        chunk_contract_id=(str(chunk_contract_id).strip() if chunk_contract_id is not None else None),
        commit_ready_b=bool(commit_ready_b),
    )


def main() -> None:
    ap = argparse.ArgumentParser(prog="re0_outbox_episode_v1")
    ap.add_argument("--outbox_root", default=".omega_cache/epistemic_outbox")
    ap.add_argument("--tick_u64", type=int, required=True)
    ap.add_argument("--raw_blob_id", action="append", required=True)
    ap.add_argument("--mob_path", action="append", required=True)
    ap.add_argument("--chunk_contract_id")
    ap.add_argument("--commit_ready_b", action="store_true")
    args = ap.parse_args()

    result = run(
        outbox_root=Path(args.outbox_root),
        tick_u64=max(0, int(args.tick_u64)),
        raw_blob_ids=[str(v) for v in args.raw_blob_id],
        mob_paths=[Path(v) for v in args.mob_path],
        chunk_contract_id=(str(args.chunk_contract_id) if args.chunk_contract_id else None),
        commit_ready_b=bool(args.commit_ready_b),
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
