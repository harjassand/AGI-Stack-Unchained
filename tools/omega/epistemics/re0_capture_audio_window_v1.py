"""RE0 AUDIO_WINDOW capture using fixture-backed byte windows."""

from __future__ import annotations

import argparse
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

_PCM16_MONO_16KHZ_BYTES_PER_MS = 32


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
    if str(payload.get("sensor_kind", "")).strip() != "AUDIO_WINDOW":
        raise RuntimeError("SCHEMA_FAIL")
    if str(payload.get("source_kind", "")).strip() not in {"AUDIO_FILE", "AUDIO_LIVE"}:
        raise RuntimeError("SCHEMA_FAIL")
    if int(payload.get("audio_window_ms_u32", 0)) <= 0:
        raise RuntimeError("SCHEMA_FAIL")
    if int(payload.get("audio_overlap_ms_u32", 0)) < 0:
        raise RuntimeError("SCHEMA_FAIL")
    return payload


def run(
    *,
    outbox_root: Path,
    episode_id: str,
    chunk_contract_path: Path,
    audio_path: Path,
    fetch_contract_id: str,
    capture_nonce_u64: int = 0,
    nonce_mode: str = "DETERMINISTIC_FROM_BYTES",
) -> dict[str, Any]:
    outbox_root = outbox_root.resolve()
    episode_id = ensure_sha256(episode_id)
    fetch_contract_id = ensure_sha256(fetch_contract_id)
    contract = _load_chunk_contract(chunk_contract_path.resolve())
    chunk_contract_id = ensure_sha256(contract.get("chunk_contract_id"))

    audio_path = audio_path.resolve()
    if not audio_path.exists() or not audio_path.is_file():
        raise RuntimeError("MISSING_INPUT")
    audio_bytes = audio_path.read_bytes()
    if not audio_bytes:
        raise RuntimeError("MISSING_INPUT")

    window_ms = int(contract.get("audio_window_ms_u32"))
    overlap_ms = int(contract.get("audio_overlap_ms_u32"))
    window_bytes = max(1, window_ms * _PCM16_MONO_16KHZ_BYTES_PER_MS)
    overlap_bytes = max(0, overlap_ms * _PCM16_MONO_16KHZ_BYTES_PER_MS)
    if overlap_bytes >= window_bytes:
        raise RuntimeError("SCHEMA_FAIL")
    step_bytes = max(1, window_bytes - overlap_bytes)

    raw_blob_ids: list[str] = []
    chunk_receipt_ids: list[str] = []
    fetch_receipt_ids: list[str] = []
    fetch_receipt_paths: list[str] = []

    chunk_index_u64 = 0
    for start in range(0, len(audio_bytes), step_bytes):
        chunk = audio_bytes[start : start + window_bytes]
        if not chunk:
            break
        raw_blob_id = hash_bytes(chunk)
        raw_blob_path = outbox_root / "blobs" / "sha256" / raw_blob_id.split(":", 1)[1]
        if raw_blob_path.exists():
            if hash_bytes(raw_blob_path.read_bytes()) != raw_blob_id:
                raise RuntimeError("HASH_MISMATCH")
        else:
            atomic_write_bytes(raw_blob_path, chunk)
        raw_blob_ids.append(raw_blob_id)

        chunk_receipt = {
            "schema_version": "epistemic_raw_chunk_v1",
            "chunk_receipt_id": "sha256:" + ("0" * 64),
            "episode_id": episode_id,
            "chunk_index_u64": int(chunk_index_u64),
            "raw_blob_id": raw_blob_id,
            "chunk_contract_id": chunk_contract_id,
        }
        chunk_receipt["chunk_receipt_id"] = canon_hash_obj({k: v for k, v in chunk_receipt.items() if k != "chunk_receipt_id"})
        chunk_receipt_id = str(chunk_receipt["chunk_receipt_id"])
        chunk_receipt_path = outbox_root / "receipts" / "chunks" / f"sha256_{chunk_receipt_id.split(':', 1)[1]}.epistemic_raw_chunk_v1.json"
        atomic_write_canon_json(chunk_receipt_path, chunk_receipt)
        chunk_receipt_ids.append(chunk_receipt_id)

        source_uri = f"{audio_path.as_uri()}#offset_bytes={start}"
        if str(nonce_mode).strip().upper() == "DETERMINISTIC_FROM_BYTES":
            capture_nonce = deterministic_nonce_u64(
                source_uri=source_uri,
                raw_blob_id=raw_blob_id,
                fetch_contract_id=fetch_contract_id,
            )
        elif str(nonce_mode).strip().upper() == "RANDOM_OK":
            capture_nonce = int((int(max(0, capture_nonce_u64)) + int(chunk_index_u64)) & ((1 << 64) - 1))
        else:
            raise RuntimeError("SCHEMA_FAIL")
        fetch_receipt = {
            "schema_version": "epistemic_fetch_receipt_v1",
            "fetch_receipt_id": "sha256:" + ("0" * 64),
            "episode_id": episode_id,
            "source_uri": source_uri,
            "status_code_u16": 200,
            "selected_headers": {
                "source_kind": str(contract.get("source_kind")),
                "chunk_index": str(chunk_index_u64),
            },
            "raw_blob_id": raw_blob_id,
            "capture_nonce_u64": int(capture_nonce),
            "fetch_contract_id": fetch_contract_id,
        }
        fetch_receipt["fetch_receipt_id"] = canon_hash_obj({k: v for k, v in fetch_receipt.items() if k != "fetch_receipt_id"})
        fetch_receipt_id = str(fetch_receipt["fetch_receipt_id"])
        fetch_receipt_path = outbox_root / "receipts" / "fetch" / f"sha256_{fetch_receipt_id.split(':', 1)[1]}.epistemic_fetch_receipt_v1.json"
        atomic_write_canon_json(fetch_receipt_path, fetch_receipt)
        fetch_receipt_ids.append(fetch_receipt_id)
        fetch_receipt_paths.append(str(fetch_receipt_path))

        chunk_index_u64 += 1

    if not raw_blob_ids:
        raise RuntimeError("MISSING_INPUT")

    pinset = {
        "schema_version": "epistemic_pinset_v1",
        "pinset_id": "sha256:" + ("0" * 64),
        "episode_id": episode_id,
        "chunk_contract_id": chunk_contract_id,
        "ordered_raw_blob_ids": list(raw_blob_ids),
        "ordered_chunk_receipt_ids": list(chunk_receipt_ids),
    }
    pinset["pinset_id"] = canon_hash_obj({k: v for k, v in pinset.items() if k != "pinset_id"})
    pinset_id = str(pinset["pinset_id"])
    pinset_path = outbox_root / "pinsets" / f"sha256_{pinset_id.split(':', 1)[1]}.epistemic_pinset_v1.json"
    atomic_write_canon_json(pinset_path, pinset)

    return {
        "episode_id": episode_id,
        "chunk_contract_id": chunk_contract_id,
        "raw_blob_ids": raw_blob_ids,
        "chunk_receipt_ids": chunk_receipt_ids,
        "pinset_id": pinset_id,
        "pinset_path": str(pinset_path),
        "fetch_receipt_ids": fetch_receipt_ids,
        "fetch_receipt_paths": fetch_receipt_paths,
    }


def main() -> None:
    ap = argparse.ArgumentParser(prog="re0_capture_audio_window_v1")
    ap.add_argument("--outbox_root", default=".omega_cache/epistemic_outbox")
    ap.add_argument("--episode_id", required=True)
    ap.add_argument("--chunk_contract_path", required=True)
    ap.add_argument("--audio_path", required=True)
    ap.add_argument("--fetch_contract_id", required=True)
    ap.add_argument("--capture_nonce_u64", type=int, default=0)
    ap.add_argument("--nonce_mode", default="DETERMINISTIC_FROM_BYTES", choices=["DETERMINISTIC_FROM_BYTES", "RANDOM_OK"])
    args = ap.parse_args()

    out = run(
        outbox_root=Path(args.outbox_root),
        episode_id=str(args.episode_id),
        chunk_contract_path=Path(args.chunk_contract_path),
        audio_path=Path(args.audio_path),
        fetch_contract_id=str(args.fetch_contract_id),
        capture_nonce_u64=max(0, int(args.capture_nonce_u64)),
        nonce_mode=str(args.nonce_mode),
    )
    print(json.dumps(out, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
