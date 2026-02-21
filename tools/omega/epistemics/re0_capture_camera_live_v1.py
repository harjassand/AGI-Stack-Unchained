"""RE0 LIVE_CAMERA fixture-backed capture into deterministic outbox artifacts."""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
from typing import Any

try:
    from .common_v1 import (
        atomic_write_bytes,
        atomic_write_canon_json,
        canon_hash_obj,
        deterministic_nonce_u64,
        ensure_sha256,
        hash_bytes,
    )
except Exception:  # pragma: no cover
    from common_v1 import (  # type: ignore
        atomic_write_bytes,
        atomic_write_canon_json,
        canon_hash_obj,
        deterministic_nonce_u64,
        ensure_sha256,
        hash_bytes,
    )


def _load_chunk_contract(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("SCHEMA_FAIL")
    if str(payload.get("schema_version", "")).strip() != "epistemic_chunk_contract_v1":
        raise RuntimeError("SCHEMA_FAIL")
    chunk_contract_id = ensure_sha256(payload.get("chunk_contract_id"))
    no_id = dict(payload)
    no_id.pop("chunk_contract_id", None)
    if canon_hash_obj(no_id) != chunk_contract_id:
        raise RuntimeError("NONDETERMINISTIC")
    if str(payload.get("sensor_kind", "")).strip() != "VISION_FRAME":
        raise RuntimeError("SCHEMA_FAIL")
    if str(payload.get("source_kind", "")).strip() != "LIVE_CAMERA":
        raise RuntimeError("SCHEMA_FAIL")
    return payload


def _nonce(
    *,
    nonce_mode: str,
    source_uri: str,
    raw_blob_id: str,
    fetch_contract_id: str,
    capture_nonce_u64: int,
    index_u64: int,
) -> int:
    mode = str(nonce_mode).strip().upper()
    if mode == "DETERMINISTIC_FROM_BYTES":
        return deterministic_nonce_u64(
            source_uri=source_uri,
            raw_blob_id=raw_blob_id,
            fetch_contract_id=fetch_contract_id,
        )
    if mode != "RANDOM_OK":
        raise RuntimeError("SCHEMA_FAIL")
    return int((int(max(0, capture_nonce_u64)) + int(index_u64)) & ((1 << 64) - 1))


def run(
    *,
    outbox_root: Path,
    episode_id: str,
    chunk_contract_path: Path,
    frame_glob: str,
    fetch_contract_id: str,
    capture_nonce_u64: int = 0,
    nonce_mode: str = "DETERMINISTIC_FROM_BYTES",
) -> dict[str, Any]:
    outbox_root = outbox_root.resolve()
    episode_id = ensure_sha256(episode_id)
    fetch_contract_id = ensure_sha256(fetch_contract_id)
    contract = _load_chunk_contract(chunk_contract_path.resolve())

    frame_paths = sorted((Path(row).resolve() for row in glob.glob(frame_glob)), key=lambda p: p.as_posix())
    frame_paths = [path for path in frame_paths if path.exists() and path.is_file()]
    if not frame_paths:
        raise RuntimeError("MISSING_INPUT")

    cadence = max(1, int(contract.get("cadence_frames_u64", 1)))
    max_frames = max(1, int(contract.get("max_frames_u64", 1)))
    selected = [path for idx, path in enumerate(frame_paths) if idx % cadence == 0][:max_frames]
    if not selected:
        raise RuntimeError("MISSING_INPUT")

    raw_blob_ids: list[str] = []
    fetch_receipt_ids: list[str] = []
    fetch_receipt_paths: list[str] = []
    for idx, path in enumerate(selected):
        raw = path.read_bytes()
        raw_blob_id = hash_bytes(raw)
        raw_blob_path = outbox_root / "blobs" / "sha256" / raw_blob_id.split(":", 1)[1]
        if raw_blob_path.exists():
            if hash_bytes(raw_blob_path.read_bytes()) != raw_blob_id:
                raise RuntimeError("HASH_MISMATCH")
        else:
            atomic_write_bytes(raw_blob_path, raw)
        raw_blob_ids.append(raw_blob_id)

        source_uri = f"camera://fixture/{path.name}"
        receipt = {
            "schema_version": "epistemic_fetch_receipt_v1",
            "fetch_receipt_id": "sha256:" + ("0" * 64),
            "episode_id": episode_id,
            "source_uri": source_uri,
            "status_code_u16": 200,
            "selected_headers": {
                "source_kind": "LIVE_CAMERA",
                "frame_index": str(idx),
            },
            "raw_blob_id": raw_blob_id,
            "capture_nonce_u64": int(
                _nonce(
                    nonce_mode=nonce_mode,
                    source_uri=source_uri,
                    raw_blob_id=raw_blob_id,
                    fetch_contract_id=fetch_contract_id,
                    capture_nonce_u64=capture_nonce_u64,
                    index_u64=idx,
                )
            ),
            "fetch_contract_id": fetch_contract_id,
        }
        receipt["fetch_receipt_id"] = canon_hash_obj({k: v for k, v in receipt.items() if k != "fetch_receipt_id"})
        receipt_id = str(receipt["fetch_receipt_id"])
        receipt_path = outbox_root / "receipts" / "fetch" / f"sha256_{receipt_id.split(':', 1)[1]}.epistemic_fetch_receipt_v1.json"
        atomic_write_canon_json(receipt_path, receipt)
        fetch_receipt_ids.append(receipt_id)
        fetch_receipt_paths.append(str(receipt_path))

    return {
        "episode_id": episode_id,
        "chunk_contract_id": str(contract.get("chunk_contract_id")),
        "raw_blob_ids": raw_blob_ids,
        "fetch_receipt_ids": fetch_receipt_ids,
        "fetch_receipt_paths": fetch_receipt_paths,
    }


def main() -> None:
    ap = argparse.ArgumentParser(prog="re0_capture_camera_live_v1")
    ap.add_argument("--outbox_root", default=".omega_cache/epistemic_outbox")
    ap.add_argument("--episode_id", required=True)
    ap.add_argument("--chunk_contract_path", required=True)
    ap.add_argument("--frame_glob", required=True)
    ap.add_argument("--fetch_contract_id", required=True)
    ap.add_argument("--capture_nonce_u64", type=int, default=0)
    ap.add_argument("--nonce_mode", default="DETERMINISTIC_FROM_BYTES", choices=["DETERMINISTIC_FROM_BYTES", "RANDOM_OK"])
    args = ap.parse_args()

    out = run(
        outbox_root=Path(args.outbox_root),
        episode_id=str(args.episode_id),
        chunk_contract_path=Path(args.chunk_contract_path),
        frame_glob=str(args.frame_glob),
        fetch_contract_id=str(args.fetch_contract_id),
        capture_nonce_u64=max(0, int(args.capture_nonce_u64)),
        nonce_mode=str(args.nonce_mode),
    )
    print(json.dumps(out, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
