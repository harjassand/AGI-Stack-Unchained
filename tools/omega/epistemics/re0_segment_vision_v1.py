"""Deterministic vision segmentation sidecar for RE0 fixed-cadence capture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .common_v1 import atomic_write_bytes, atomic_write_canon_json, canon_bytes, canon_hash_obj, ensure_sha256, hash_bytes
except Exception:  # pragma: no cover
    from common_v1 import atomic_write_bytes, atomic_write_canon_json, canon_bytes, canon_hash_obj, ensure_sha256, hash_bytes


def _segment_payload(*, episode_id: str, raw_blob_id: str, segment_index_u64: int, raw_bytes: bytes) -> dict[str, Any]:
    return {
        "schema_version": "epistemic_vision_segment_v1",
        "segment_id": "sha256:" + ("0" * 64),
        "episode_id": episode_id,
        "raw_blob_id": raw_blob_id,
        "segment_index_u64": int(segment_index_u64),
        "byte_len_u64": int(len(raw_bytes)),
        "preview_sha256_prefix": raw_blob_id.split(":", 1)[1][:16],
    }


def run(
    *,
    outbox_root: Path,
    episode_id: str,
    raw_blob_ids: list[str],
    segment_contract_id: str,
) -> dict[str, Any]:
    outbox_root = outbox_root.resolve()
    episode_id = ensure_sha256(episode_id)
    segment_contract_id = ensure_sha256(segment_contract_id)
    if not raw_blob_ids:
        raise RuntimeError("SCHEMA_FAIL")

    input_blob_ids = [ensure_sha256(row) for row in raw_blob_ids]
    output_blob_ids: list[str] = []
    for idx, raw_blob_id in enumerate(input_blob_ids):
        raw_path = outbox_root / "blobs" / "sha256" / raw_blob_id.split(":", 1)[1]
        if not raw_path.exists() or not raw_path.is_file():
            raise RuntimeError("MISSING_INPUT")
        raw = raw_path.read_bytes()
        if hash_bytes(raw) != raw_blob_id:
            raise RuntimeError("HASH_MISMATCH")
        payload = _segment_payload(
            episode_id=episode_id,
            raw_blob_id=raw_blob_id,
            segment_index_u64=idx,
            raw_bytes=raw,
        )
        payload["segment_id"] = canon_hash_obj({k: v for k, v in payload.items() if k != "segment_id"})
        segment_blob = canon_bytes(payload)
        segment_blob_id = hash_bytes(segment_blob)
        output_blob_ids.append(segment_blob_id)
        segment_blob_path = outbox_root / "blobs" / "sha256" / segment_blob_id.split(":", 1)[1]
        if segment_blob_path.exists():
            if hash_bytes(segment_blob_path.read_bytes()) != segment_blob_id:
                raise RuntimeError("HASH_MISMATCH")
        else:
            atomic_write_bytes(segment_blob_path, segment_blob)

    ordering_hash = canon_hash_obj(
        {
            "schema_version": "epistemic_segment_ordering_v1",
            "input_blob_ids": input_blob_ids,
            "output_blob_ids": output_blob_ids,
        }
    )
    receipt = {
        "schema_version": "epistemic_segment_receipt_v1",
        "segment_receipt_id": "sha256:" + ("0" * 64),
        "episode_id": episode_id,
        "segment_contract_id": segment_contract_id,
        "input_blob_ids": input_blob_ids,
        "output_blob_ids": output_blob_ids,
        "ordering_hash": ordering_hash,
        "segment_count_u64": int(len(output_blob_ids)),
    }
    receipt["segment_receipt_id"] = canon_hash_obj({k: v for k, v in receipt.items() if k != "segment_receipt_id"})
    receipt_path = (
        outbox_root
        / "receipts"
        / "segments"
        / f"sha256_{str(receipt['segment_receipt_id']).split(':', 1)[1]}.epistemic_segment_receipt_v1.json"
    )
    atomic_write_canon_json(receipt_path, receipt)

    return {
        "episode_id": episode_id,
        "segment_receipt_id": str(receipt["segment_receipt_id"]),
        "segment_receipt_path": str(receipt_path),
        "output_blob_ids": output_blob_ids,
    }


def main() -> None:
    ap = argparse.ArgumentParser(prog="re0_segment_vision_v1")
    ap.add_argument("--outbox_root", default=".omega_cache/epistemic_outbox")
    ap.add_argument("--episode_id", required=True)
    ap.add_argument("--segment_contract_id", required=True)
    ap.add_argument("--raw_blob_id", action="append", required=True)
    args = ap.parse_args()
    result = run(
        outbox_root=Path(args.outbox_root),
        episode_id=str(args.episode_id),
        raw_blob_ids=[str(row) for row in args.raw_blob_id],
        segment_contract_id=str(args.segment_contract_id),
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
