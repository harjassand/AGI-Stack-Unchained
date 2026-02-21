"""RE0 vision capture sidecar (fixed cadence, file/video sources)."""

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
    from .re0_capture_video_pinned_decode_v1 import run as run_video_pinned_decode
except Exception:  # pragma: no cover
    from common_v1 import (  # type: ignore
        atomic_write_bytes,
        atomic_write_canon_json,
        canon_hash_obj,
        deterministic_nonce_u64,
        ensure_sha256,
        hash_bytes,
    )
    from re0_capture_video_pinned_decode_v1 import run as run_video_pinned_decode  # type: ignore


def _load_chunk_contract(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("SCHEMA_FAIL")
    if str(payload.get("schema_version", "")).strip() != "epistemic_chunk_contract_v1":
        raise RuntimeError("SCHEMA_FAIL")
    contract_id = ensure_sha256(payload.get("chunk_contract_id"))
    no_id = dict(payload)
    no_id.pop("chunk_contract_id", None)
    if canon_hash_obj(no_id) != contract_id:
        raise RuntimeError("NONDETERMINISTIC")
    return payload


def _frame_sources(source_kind: str, *, input_glob: str | None) -> list[Path]:
    if source_kind == "FILE_SEQUENCE":
        if not input_glob:
            raise RuntimeError("SCHEMA_FAIL")
        rows = sorted((Path(path).resolve() for path in glob.glob(input_glob)), key=lambda p: p.as_posix())
        frames = [path for path in rows if path.exists() and path.is_file()]
        if not frames:
            raise RuntimeError("MISSING_INPUT")
        return frames
    raise RuntimeError("SCHEMA_FAIL")


def _capture_nonce(
    *,
    nonce_mode: str,
    source_uri: str,
    raw_blob_id: str,
    fetch_contract_id: str,
    capture_nonce_u64: int,
    frame_index: int,
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
    return int((int(max(0, capture_nonce_u64)) + int(frame_index)) & ((1 << 64) - 1))


def run(
    *,
    outbox_root: Path,
    episode_id: str,
    chunk_contract_path: Path,
    source_kind: str,
    input_glob: str | None,
    video_path: Path | None,
    fetch_contract_id: str,
    capture_nonce_u64: int,
    nonce_mode: str = "DETERMINISTIC_FROM_BYTES",
    decoder_contract_path: Path | None = None,
) -> dict[str, Any]:
    outbox_root = outbox_root.resolve()
    episode_id = ensure_sha256(episode_id)
    fetch_contract_id = ensure_sha256(fetch_contract_id)

    chunk_contract = _load_chunk_contract(chunk_contract_path.resolve())
    if str(chunk_contract.get("sensor_kind", "")).strip() != "VISION_FRAME":
        raise RuntimeError("SCHEMA_FAIL")
    if str(chunk_contract.get("source_kind", "")).strip() != str(source_kind).strip():
        raise RuntimeError("SCHEMA_FAIL")

    cadence = max(1, int(chunk_contract.get("cadence_frames_u64", 1)))
    max_frames = max(1, int(chunk_contract.get("max_frames_u64", 1)))
    source_kind = str(source_kind).strip()
    if source_kind == "VIDEO_FILE":
        if video_path is None or decoder_contract_path is None:
            raise RuntimeError("VIDEO_SOURCE_DISABLED_UNTIL_DECODE_CONTRACT")
        expected_decoder_id = ensure_sha256(chunk_contract.get("decoder_contract_id"))
        decode = run_video_pinned_decode(
            outbox_root=outbox_root,
            episode_id=episode_id,
            video_path=video_path.resolve(),
            decoder_contract_path=decoder_contract_path.resolve(),
            fetch_contract_id=fetch_contract_id,
            capture_nonce_u64=int(max(0, capture_nonce_u64)),
            nonce_mode=str(nonce_mode).strip().upper(),
            write_fetch_receipts=True,
        )
        if ensure_sha256(decode.get("decoder_contract_id")) != expected_decoder_id:
            raise RuntimeError("PIN_HASH_MISMATCH")
        frame_ids = [ensure_sha256(row) for row in list(decode.get("raw_blob_ids") or [])]
        selected_ids = [blob_id for idx, blob_id in enumerate(frame_ids) if idx % cadence == 0][:max_frames]
        if not selected_ids:
            raise RuntimeError("MISSING_INPUT")
        selected_set = set(selected_ids)
        selected_fetch_ids: list[str] = []
        selected_fetch_paths: list[str] = []
        for fetch_path_raw in list(decode.get("fetch_receipt_paths") or []):
            fetch_path = Path(str(fetch_path_raw))
            if not fetch_path.exists() or not fetch_path.is_file():
                raise RuntimeError("MISSING_INPUT")
            payload = json.loads(fetch_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise RuntimeError("SCHEMA_FAIL")
            raw_blob_id = ensure_sha256(payload.get("raw_blob_id"))
            if raw_blob_id not in selected_set:
                continue
            selected_fetch_ids.append(ensure_sha256(payload.get("fetch_receipt_id")))
            selected_fetch_paths.append(str(fetch_path))
        return {
            "episode_id": episode_id,
            "chunk_contract_id": str(chunk_contract.get("chunk_contract_id")),
            "raw_blob_ids": list(selected_ids),
            "fetch_receipt_ids": selected_fetch_ids,
            "fetch_receipt_paths": selected_fetch_paths,
            "decoder_repro_receipt_id": str(decode.get("decoder_repro_receipt_id", "")),
            "decoder_repro_receipt_path": str(decode.get("decoder_repro_receipt_path", "")),
        }

    sources = _frame_sources(source_kind, input_glob=input_glob)
    selected = [path for idx, path in enumerate(sources) if idx % cadence == 0][:max_frames]
    if not selected:
        raise RuntimeError("MISSING_INPUT")

    raw_blob_ids: list[str] = []
    fetch_receipt_ids: list[str] = []
    fetch_receipt_paths: list[str] = []
    for frame_index, source_path in enumerate(selected):
        blob = source_path.read_bytes()
        raw_blob_id = hash_bytes(blob)
        raw_blob_ids.append(raw_blob_id)
        blob_path = outbox_root / "blobs" / "sha256" / raw_blob_id.split(":", 1)[1]
        if blob_path.exists():
            if hash_bytes(blob_path.read_bytes()) != raw_blob_id:
                raise RuntimeError("HASH_MISMATCH")
        else:
            atomic_write_bytes(blob_path, blob)

        receipt = {
            "schema_version": "epistemic_fetch_receipt_v1",
            "fetch_receipt_id": "sha256:" + ("0" * 64),
            "episode_id": episode_id,
            "source_uri": source_path.as_uri(),
            "status_code_u16": 200,
            "selected_headers": {
                "source_kind": str(source_kind),
                "frame_index": str(frame_index),
            },
            "raw_blob_id": raw_blob_id,
            "capture_nonce_u64": int(
                _capture_nonce(
                    nonce_mode=str(nonce_mode),
                    source_uri=source_path.as_uri(),
                    raw_blob_id=raw_blob_id,
                    fetch_contract_id=fetch_contract_id,
                    capture_nonce_u64=int(max(0, capture_nonce_u64)),
                    frame_index=frame_index,
                )
            ),
            "fetch_contract_id": fetch_contract_id,
        }
        receipt["fetch_receipt_id"] = canon_hash_obj({k: v for k, v in receipt.items() if k != "fetch_receipt_id"})
        receipt_id = str(receipt["fetch_receipt_id"])
        atomic_write_canon_json(
            outbox_root / "receipts" / "fetch" / f"sha256_{receipt_id.split(':', 1)[1]}.epistemic_fetch_receipt_v1.json",
            receipt,
        )
        fetch_receipt_ids.append(receipt_id)
        fetch_receipt_paths.append(
            str(outbox_root / "receipts" / "fetch" / f"sha256_{receipt_id.split(':', 1)[1]}.epistemic_fetch_receipt_v1.json")
        )

    return {
        "episode_id": episode_id,
        "chunk_contract_id": str(chunk_contract.get("chunk_contract_id")),
        "raw_blob_ids": raw_blob_ids,
        "fetch_receipt_ids": fetch_receipt_ids,
        "fetch_receipt_paths": fetch_receipt_paths,
    }


def main() -> None:
    ap = argparse.ArgumentParser(prog="re0_capture_vision_fixed_cadence_v1")
    ap.add_argument("--outbox_root", default=".omega_cache/epistemic_outbox")
    ap.add_argument("--episode_id", required=True)
    ap.add_argument("--chunk_contract_path", required=True)
    ap.add_argument("--source_kind", required=True, choices=["FILE_SEQUENCE", "VIDEO_FILE"])
    ap.add_argument("--input_glob")
    ap.add_argument("--video_path")
    ap.add_argument("--decoder_contract_path")
    ap.add_argument("--fetch_contract_id", required=True)
    ap.add_argument("--capture_nonce_u64", type=int, default=0)
    ap.add_argument("--nonce_mode", default="DETERMINISTIC_FROM_BYTES", choices=["DETERMINISTIC_FROM_BYTES", "RANDOM_OK"])
    args = ap.parse_args()
    result = run(
        outbox_root=Path(args.outbox_root),
        episode_id=str(args.episode_id),
        chunk_contract_path=Path(args.chunk_contract_path),
        source_kind=str(args.source_kind),
        input_glob=(str(args.input_glob) if args.input_glob else None),
        video_path=(Path(args.video_path) if args.video_path else None),
        decoder_contract_path=(Path(args.decoder_contract_path) if args.decoder_contract_path else None),
        fetch_contract_id=str(args.fetch_contract_id),
        capture_nonce_u64=max(0, int(args.capture_nonce_u64)),
        nonce_mode=str(args.nonce_mode),
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
