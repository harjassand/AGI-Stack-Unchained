"""Pinned deterministic VIDEO_FILE decoder for RE0 capture."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
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
        hash_file,
    )
except Exception:  # pragma: no cover
    from common_v1 import (  # type: ignore
        atomic_write_bytes,
        atomic_write_canon_json,
        canon_hash_obj,
        deterministic_nonce_u64,
        ensure_sha256,
        hash_bytes,
        hash_file,
    )


def _load_decoder_contract(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("SCHEMA_FAIL")
    if str(payload.get("schema_version", "")).strip() != "epistemic_decoder_contract_v1":
        raise RuntimeError("SCHEMA_FAIL")
    decoder_contract_id = ensure_sha256(payload.get("decoder_contract_id"))
    no_id = dict(payload)
    no_id.pop("decoder_contract_id", None)
    if canon_hash_obj(no_id) != decoder_contract_id:
        raise RuntimeError("NONDETERMINISTIC")

    if int(payload.get("threads_u32", -1)) != 1:
        raise RuntimeError("DECODE_ARGS_MISMATCH")
    if str(payload.get("hwaccel_mode", "")).strip() != "none":
        raise RuntimeError("DECODE_ARGS_MISMATCH")

    ffmpeg_exe_path = Path(str(payload.get("ffmpeg_exe_path", "")).strip()).resolve()
    if not ffmpeg_exe_path.exists() or not ffmpeg_exe_path.is_file():
        raise RuntimeError("MISSING_INPUT")
    expected_exe_hash = ensure_sha256(payload.get("ffmpeg_exe_sha256"))
    if hash_file(ffmpeg_exe_path) != expected_exe_hash:
        raise RuntimeError("PIN_HASH_MISMATCH")

    frame_mode = str(payload.get("frame_selection_mode", "")).strip()
    if frame_mode == "FRAME_INDEX_STRIDE":
        if int(payload.get("frame_stride_u32", 0)) <= 0:
            raise RuntimeError("SCHEMA_FAIL")
    elif frame_mode == "PTS_QUANTIZED":
        if int(payload.get("pts_timebase_num_u32", 0)) <= 0:
            raise RuntimeError("SCHEMA_FAIL")
        if int(payload.get("pts_timebase_den_u32", 0)) <= 0:
            raise RuntimeError("SCHEMA_FAIL")
        if int(payload.get("pts_quantum_u64", 0)) <= 0:
            raise RuntimeError("SCHEMA_FAIL")
    else:
        raise RuntimeError("SCHEMA_FAIL")

    if not str(payload.get("pixel_format", "")).strip() or not str(payload.get("vf_filter", "")).strip():
        raise RuntimeError("SCHEMA_FAIL")
    payload["ffmpeg_exe_path"] = str(ffmpeg_exe_path)
    return payload


def _selection_filter(contract: dict[str, Any]) -> str:
    mode = str(contract.get("frame_selection_mode", "")).strip()
    if mode == "FRAME_INDEX_STRIDE":
        stride = int(contract.get("frame_stride_u32", 1))
        return f"select=not(mod(n\\,{stride}))"
    num = int(contract.get("pts_timebase_num_u32", 1))
    den = int(contract.get("pts_timebase_den_u32", 1))
    quantum = int(contract.get("pts_quantum_u64", 1))
    return f"select=not(mod(floor(pts*{den}/{num})\\,{quantum}))"


def _decode_once(*, video_path: Path, contract: dict[str, Any], out_dir: Path) -> list[Path]:
    selection = _selection_filter(contract)
    vf_filter = str(contract.get("vf_filter", "")).strip()
    vf_expr = f"{vf_filter},{selection}" if vf_filter else selection
    output_pattern = out_dir / "frame_%010d.ppm"
    cmd = [
        str(contract.get("ffmpeg_exe_path")),
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-threads",
        "1",
        "-hwaccel",
        "none",
        "-i",
        str(video_path),
        "-vf",
        vf_expr,
        "-pix_fmt",
        str(contract.get("pixel_format")),
        "-vsync",
        "0",
        "-f",
        "image2",
        str(output_pattern),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError("DECODER_RUN_FAIL")
    frames = sorted(out_dir.glob("frame_*.ppm"), key=lambda p: p.name)
    if not frames:
        raise RuntimeError("DECODER_EMPTY")
    return frames


def _frame_ids(paths: list[Path]) -> tuple[list[str], dict[str, bytes]]:
    ids: list[str] = []
    bytes_by_id: dict[str, bytes] = {}
    for path in paths:
        blob = path.read_bytes()
        blob_id = hash_bytes(blob)
        ids.append(blob_id)
        bytes_by_id[blob_id] = blob
    return ids, bytes_by_id


def _frame_id_list_hash(frame_ids: list[str]) -> str:
    return canon_hash_obj(
        {
            "schema_version": "epistemic_decoder_frame_id_list_v1",
            "frame_blob_ids": list(frame_ids),
        }
    )


def _capture_nonce(
    *,
    nonce_mode: str,
    source_uri: str,
    raw_blob_id: str,
    fetch_contract_id: str,
    capture_nonce_u64: int,
) -> int:
    if nonce_mode == "DETERMINISTIC_FROM_BYTES":
        return deterministic_nonce_u64(
            source_uri=source_uri,
            raw_blob_id=raw_blob_id,
            fetch_contract_id=fetch_contract_id,
        )
    if nonce_mode != "RANDOM_OK":
        raise RuntimeError("SCHEMA_FAIL")
    seed = int.from_bytes(os.urandom(8), "big", signed=False)
    return int((seed + int(max(0, capture_nonce_u64))) & ((1 << 64) - 1))


def run(
    *,
    outbox_root: Path,
    episode_id: str,
    video_path: Path,
    decoder_contract_path: Path,
    fetch_contract_id: str,
    capture_nonce_u64: int = 0,
    nonce_mode: str = "DETERMINISTIC_FROM_BYTES",
    write_fetch_receipts: bool = True,
) -> dict[str, Any]:
    outbox_root = outbox_root.resolve()
    episode_id = ensure_sha256(episode_id)
    fetch_contract_id = ensure_sha256(fetch_contract_id)
    video_path = video_path.resolve()
    if not video_path.exists() or not video_path.is_file():
        raise RuntimeError("MISSING_INPUT")
    contract = _load_decoder_contract(decoder_contract_path.resolve())
    decoder_contract_id = ensure_sha256(contract.get("decoder_contract_id"))

    source_blob = video_path.read_bytes()
    source_blob_id = hash_bytes(source_blob)
    source_blob_path = outbox_root / "blobs" / "sha256" / source_blob_id.split(":", 1)[1]
    if source_blob_path.exists():
        if hash_bytes(source_blob_path.read_bytes()) != source_blob_id:
            raise RuntimeError("HASH_MISMATCH")
    else:
        atomic_write_bytes(source_blob_path, source_blob)

    tmp_parent = Path(tempfile.mkdtemp(prefix="re0_video_decode_"))
    try:
        run1_dir = tmp_parent / "run1"
        run2_dir = tmp_parent / "run2"
        run1_dir.mkdir(parents=True, exist_ok=True)
        run2_dir.mkdir(parents=True, exist_ok=True)
        run1_frames = _decode_once(video_path=video_path, contract=contract, out_dir=run1_dir)
        run1_ids, run1_bytes_by_id = _frame_ids(run1_frames)
        run2_frames = _decode_once(video_path=video_path, contract=contract, out_dir=run2_dir)
        run2_ids, _run2_bytes_by_id = _frame_ids(run2_frames)
    finally:
        shutil.rmtree(tmp_parent, ignore_errors=True)

    run1_hash = _frame_id_list_hash(run1_ids)
    run2_hash = _frame_id_list_hash(run2_ids)
    outcome = "PASS" if run1_ids == run2_ids else "FAIL"
    reason_code = "REPRO_PASS" if outcome == "PASS" else "REPRO_MISMATCH"

    repro_receipt = {
        "schema_version": "epistemic_decoder_repro_receipt_v1",
        "repro_receipt_id": "sha256:" + ("0" * 64),
        "decoder_contract_id": decoder_contract_id,
        "source_blob_id": source_blob_id,
        "run1_frame_ids_hash": run1_hash,
        "run2_frame_ids_hash": run2_hash,
        "outcome": outcome,
        "reason_code": reason_code,
    }
    repro_receipt["repro_receipt_id"] = canon_hash_obj({k: v for k, v in repro_receipt.items() if k != "repro_receipt_id"})
    repro_receipt_id = str(repro_receipt["repro_receipt_id"])
    repro_receipt_path = (
        outbox_root
        / "receipts"
        / "decoder"
        / f"sha256_{repro_receipt_id.split(':', 1)[1]}.epistemic_decoder_repro_receipt_v1.json"
    )
    atomic_write_canon_json(repro_receipt_path, repro_receipt)

    if outcome != "PASS":
        raise RuntimeError("DECODER_REPRO_FAIL")

    fetch_receipt_ids: list[str] = []
    fetch_receipt_paths: list[str] = []
    for idx, raw_blob_id in enumerate(run1_ids):
        blob = run1_bytes_by_id[raw_blob_id]
        blob_path = outbox_root / "blobs" / "sha256" / raw_blob_id.split(":", 1)[1]
        if blob_path.exists():
            if hash_bytes(blob_path.read_bytes()) != raw_blob_id:
                raise RuntimeError("HASH_MISMATCH")
        else:
            atomic_write_bytes(blob_path, blob)
        if not write_fetch_receipts:
            continue
        source_uri = f"{video_path.as_uri()}#frame_index={idx}"
        nonce = _capture_nonce(
            nonce_mode=str(nonce_mode).strip().upper(),
            source_uri=source_uri,
            raw_blob_id=raw_blob_id,
            fetch_contract_id=fetch_contract_id,
            capture_nonce_u64=int(max(0, capture_nonce_u64)),
        )
        fetch_receipt = {
            "schema_version": "epistemic_fetch_receipt_v1",
            "fetch_receipt_id": "sha256:" + ("0" * 64),
            "episode_id": episode_id,
            "source_uri": source_uri,
            "status_code_u16": 200,
            "selected_headers": {
                "source_kind": "VIDEO_FILE",
                "frame_index": str(idx),
                "decoder_contract_id": decoder_contract_id,
            },
            "raw_blob_id": raw_blob_id,
            "capture_nonce_u64": int(nonce),
            "fetch_contract_id": fetch_contract_id,
        }
        fetch_receipt["fetch_receipt_id"] = canon_hash_obj(
            {k: v for k, v in fetch_receipt.items() if k != "fetch_receipt_id"}
        )
        fetch_receipt_id = str(fetch_receipt["fetch_receipt_id"])
        fetch_receipt_path = (
            outbox_root
            / "receipts"
            / "fetch"
            / f"sha256_{fetch_receipt_id.split(':', 1)[1]}.epistemic_fetch_receipt_v1.json"
        )
        atomic_write_canon_json(fetch_receipt_path, fetch_receipt)
        fetch_receipt_ids.append(fetch_receipt_id)
        fetch_receipt_paths.append(str(fetch_receipt_path))

    return {
        "episode_id": episode_id,
        "decoder_contract_id": decoder_contract_id,
        "source_blob_id": source_blob_id,
        "raw_blob_ids": list(run1_ids),
        "run1_frame_ids_hash": run1_hash,
        "run2_frame_ids_hash": run2_hash,
        "decoder_repro_receipt_id": repro_receipt_id,
        "decoder_repro_receipt_path": str(repro_receipt_path),
        "fetch_receipt_ids": fetch_receipt_ids,
        "fetch_receipt_paths": fetch_receipt_paths,
    }


def main() -> None:
    ap = argparse.ArgumentParser(prog="re0_capture_video_pinned_decode_v1")
    ap.add_argument("--outbox_root", default=".omega_cache/epistemic_outbox")
    ap.add_argument("--episode_id", required=True)
    ap.add_argument("--video_path", required=True)
    ap.add_argument("--decoder_contract_path", required=True)
    ap.add_argument("--fetch_contract_id", required=True)
    ap.add_argument("--capture_nonce_u64", type=int, default=0)
    ap.add_argument("--nonce_mode", default="DETERMINISTIC_FROM_BYTES", choices=["DETERMINISTIC_FROM_BYTES", "RANDOM_OK"])
    ap.add_argument("--no_fetch_receipts", action="store_true")
    args = ap.parse_args()

    result = run(
        outbox_root=Path(args.outbox_root),
        episode_id=str(args.episode_id),
        video_path=Path(args.video_path),
        decoder_contract_path=Path(args.decoder_contract_path),
        fetch_contract_id=str(args.fetch_contract_id),
        capture_nonce_u64=max(0, int(args.capture_nonce_u64)),
        nonce_mode=str(args.nonce_mode),
        write_fetch_receipts=(not bool(args.no_fetch_receipts)),
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
