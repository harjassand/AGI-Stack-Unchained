"""RE0 BYTE_STREAM_RABIN chunker with pinned rolling fingerprint contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .common_v1 import atomic_write_bytes, atomic_write_canon_json, canon_hash_obj, ensure_sha256, hash_bytes
except Exception:  # pragma: no cover
    from common_v1 import atomic_write_bytes, atomic_write_canon_json, canon_hash_obj, ensure_sha256, hash_bytes  # type: ignore

_U64_MASK = (1 << 64) - 1


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
    if str(payload.get("sensor_kind", "")).strip() != "BYTE_STREAM_RABIN":
        raise RuntimeError("SCHEMA_FAIL")
    if str(payload.get("source_kind", "")).strip() != "BYTE_STREAM_FILE":
        raise RuntimeError("SCHEMA_FAIL")

    min_chunk = int(payload.get("min_chunk_bytes_u32", 0))
    max_chunk = int(payload.get("max_chunk_bytes_u32", 0))
    window = int(payload.get("rabin_window_bytes_u32", 0))
    poly = int(payload.get("rabin_polynomial_u64", 0))
    mask = int(payload.get("rabin_mask_u64", 0))
    if min_chunk <= 0 or max_chunk <= 0 or min_chunk > max_chunk:
        raise RuntimeError("SCHEMA_FAIL")
    if window <= 0 or poly <= 0 or mask <= 0:
        raise RuntimeError("SCHEMA_FAIL")
    return payload


def _rabin_chunks(
    *,
    data: bytes,
    polynomial_u64: int,
    window_bytes: int,
    mask_u64: int,
    min_chunk_bytes: int,
    max_chunk_bytes: int,
) -> list[bytes]:
    if not data:
        return []
    base = int(polynomial_u64) & _U64_MASK
    mask = int(mask_u64) & _U64_MASK
    window = int(window_bytes)
    base_pow = pow(base, max(0, window - 1), 1 << 64)

    out: list[bytes] = []
    start = 0
    n = len(data)
    while start < n:
        hard_end = min(n, start + max_chunk_bytes)
        fp = 0
        cut = hard_end
        for i in range(start, hard_end):
            b = int(data[i])
            if i - start < window:
                fp = ((fp * base) + b) & _U64_MASK
            else:
                out_b = int(data[i - window])
                fp = (fp - ((out_b * base_pow) & _U64_MASK)) & _U64_MASK
                fp = ((fp * base) + b) & _U64_MASK
            chunk_len = (i - start) + 1
            if chunk_len < min_chunk_bytes:
                continue
            if (fp & mask) == 0:
                cut = i + 1
                break
        if cut <= start:
            cut = min(n, start + max(1, min_chunk_bytes))
        out.append(data[start:cut])
        start = cut
    return out


def run(
    *,
    outbox_root: Path,
    episode_id: str,
    chunk_contract_path: Path,
    input_path: Path,
) -> dict[str, Any]:
    outbox_root = outbox_root.resolve()
    episode_id = ensure_sha256(episode_id)
    contract = _load_chunk_contract(chunk_contract_path.resolve())
    chunk_contract_id = ensure_sha256(contract.get("chunk_contract_id"))

    input_path = input_path.resolve()
    if not input_path.exists() or not input_path.is_file():
        raise RuntimeError("MISSING_INPUT")
    data = input_path.read_bytes()
    if not data:
        raise RuntimeError("MISSING_INPUT")

    chunks = _rabin_chunks(
        data=data,
        polynomial_u64=int(contract.get("rabin_polynomial_u64")),
        window_bytes=int(contract.get("rabin_window_bytes_u32")),
        mask_u64=int(contract.get("rabin_mask_u64")),
        min_chunk_bytes=int(contract.get("min_chunk_bytes_u32")),
        max_chunk_bytes=int(contract.get("max_chunk_bytes_u32")),
    )
    if not chunks:
        raise RuntimeError("MISSING_INPUT")

    raw_blob_ids: list[str] = []
    chunk_receipt_ids: list[str] = []
    for idx, chunk in enumerate(chunks):
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
            "chunk_index_u64": int(idx),
            "raw_blob_id": raw_blob_id,
            "chunk_contract_id": chunk_contract_id,
        }
        chunk_receipt["chunk_receipt_id"] = canon_hash_obj({k: v for k, v in chunk_receipt.items() if k != "chunk_receipt_id"})
        chunk_receipt_id = str(chunk_receipt["chunk_receipt_id"])
        chunk_receipt_path = outbox_root / "receipts" / "chunks" / f"sha256_{chunk_receipt_id.split(':', 1)[1]}.epistemic_raw_chunk_v1.json"
        atomic_write_canon_json(chunk_receipt_path, chunk_receipt)
        chunk_receipt_ids.append(chunk_receipt_id)

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
    }


def main() -> None:
    ap = argparse.ArgumentParser(prog="re0_chunk_bytestream_rabin_v1")
    ap.add_argument("--outbox_root", default=".omega_cache/epistemic_outbox")
    ap.add_argument("--episode_id", required=True)
    ap.add_argument("--chunk_contract_path", required=True)
    ap.add_argument("--input_path", required=True)
    args = ap.parse_args()

    out = run(
        outbox_root=Path(args.outbox_root),
        episode_id=str(args.episode_id),
        chunk_contract_path=Path(args.chunk_contract_path),
        input_path=Path(args.input_path),
    )
    print(json.dumps(out, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
