"""RE0 LIVE_WEB HTML segmentation with enforceable implementation pinning."""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any

try:
    from .common_v1 import (
        atomic_write_bytes,
        atomic_write_canon_json,
        canon_bytes,
        canon_hash_obj,
        ensure_sha256,
        hash_bytes,
        hash_file,
    )
except Exception:  # pragma: no cover
    from common_v1 import (  # type: ignore
        atomic_write_bytes,
        atomic_write_canon_json,
        canon_bytes,
        canon_hash_obj,
        ensure_sha256,
        hash_bytes,
        hash_file,
    )

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\n]+")


def _strip_html(raw_bytes: bytes) -> str:
    text = raw_bytes.decode("utf-8", errors="replace")
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = _WS_RE.sub(" ", text)
    return text.strip()


def _segment(text: str, *, max_segment_len: int) -> list[str]:
    if not text:
        return []
    pieces = [chunk.strip() for chunk in re.split(r"(?<=[.!?])\s+", text) if chunk.strip()]
    out: list[str] = []
    for piece in pieces:
        chunk = piece
        while len(chunk) > max_segment_len:
            out.append(chunk[:max_segment_len])
            chunk = chunk[max_segment_len:]
        if chunk:
            out.append(chunk)
    return out


def _load_segment_contract(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("SCHEMA_FAIL")
    if str(payload.get("schema_version", "")).strip() != "epistemic_segment_contract_v1":
        raise RuntimeError("SCHEMA_FAIL")
    segment_contract_id = ensure_sha256(payload.get("segment_contract_id"))
    no_id = dict(payload)
    no_id.pop("segment_contract_id", None)
    if canon_hash_obj(no_id) != segment_contract_id:
        raise RuntimeError("NONDETERMINISTIC")

    impl_rel = str(payload.get("segmenter_impl_relpath", "")).strip()
    if not impl_rel:
        raise RuntimeError("SCHEMA_FAIL")
    impl_path = Path(impl_rel)
    if impl_path.is_absolute() or ".." in impl_path.parts:
        raise RuntimeError("SCHEMA_FAIL")
    impl_abs = (Path.cwd() / impl_path).resolve()
    if not impl_abs.exists() or not impl_abs.is_file():
        raise RuntimeError("MISSING_INPUT")
    impl_sha = ensure_sha256(payload.get("segmenter_impl_sha256"))
    if hash_file(impl_abs) != impl_sha:
        raise RuntimeError("PIN_HASH_MISMATCH")

    ordering_rule = str(payload.get("ordering_rule", "")).strip()
    if ordering_rule not in {"INPUT_BLOB_ID_ASC", "SEGMENT_INDEX_ASC"}:
        raise RuntimeError("SCHEMA_FAIL")

    payload["segmenter_impl_relpath"] = impl_rel
    return payload


def run(
    *,
    outbox_root: Path,
    episode_id: str,
    input_blob_ids: list[str],
    segment_contract_path: Path,
) -> dict[str, Any]:
    outbox_root = outbox_root.resolve()
    episode_id = ensure_sha256(episode_id)
    contract = _load_segment_contract(segment_contract_path.resolve())
    segment_contract_id = ensure_sha256(contract.get("segment_contract_id"))
    max_segment_len = int(contract.get("max_segment_len_u32", 2048))
    max_segment_len = max(1, max_segment_len)

    normalized_inputs = [ensure_sha256(row) for row in input_blob_ids]
    if not normalized_inputs:
        raise RuntimeError("SCHEMA_FAIL")
    ordering_rule = str(contract.get("ordering_rule", "INPUT_BLOB_ID_ASC"))
    if ordering_rule == "INPUT_BLOB_ID_ASC":
        normalized_inputs = sorted(set(normalized_inputs))

    output_blob_ids: list[str] = []
    output_index_u64 = 0
    for raw_blob_id in normalized_inputs:
        blob_path = outbox_root / "blobs" / "sha256" / raw_blob_id.split(":", 1)[1]
        if not blob_path.exists() or not blob_path.is_file():
            raise RuntimeError("MISSING_INPUT")
        raw = blob_path.read_bytes()
        if hash_bytes(raw) != raw_blob_id:
            raise RuntimeError("HASH_MISMATCH")
        segments = _segment(_strip_html(raw), max_segment_len=max_segment_len)
        for segment in segments:
            payload = {
                "schema_version": "epistemic_html_segment_v1",
                "segment_id": "sha256:" + ("0" * 64),
                "episode_id": episode_id,
                "raw_blob_id": raw_blob_id,
                "segment_index_u64": int(output_index_u64),
                "text": str(segment),
            }
            payload["segment_id"] = canon_hash_obj({k: v for k, v in payload.items() if k != "segment_id"})
            blob = canon_bytes(payload)
            segment_blob_id = hash_bytes(blob)
            segment_blob_path = outbox_root / "blobs" / "sha256" / segment_blob_id.split(":", 1)[1]
            if segment_blob_path.exists():
                if hash_bytes(segment_blob_path.read_bytes()) != segment_blob_id:
                    raise RuntimeError("HASH_MISMATCH")
            else:
                atomic_write_bytes(segment_blob_path, blob)
            output_blob_ids.append(segment_blob_id)
            output_index_u64 += 1

    if not output_blob_ids:
        # deterministic empty segment marker
        payload = {
            "schema_version": "epistemic_html_segment_v1",
            "segment_id": "sha256:" + ("0" * 64),
            "episode_id": episode_id,
            "raw_blob_id": normalized_inputs[0],
            "segment_index_u64": 0,
            "text": "",
        }
        payload["segment_id"] = canon_hash_obj({k: v for k, v in payload.items() if k != "segment_id"})
        blob = canon_bytes(payload)
        segment_blob_id = hash_bytes(blob)
        atomic_write_bytes(outbox_root / "blobs" / "sha256" / segment_blob_id.split(":", 1)[1], blob)
        output_blob_ids.append(segment_blob_id)

    ordering_hash = canon_hash_obj(
        {
            "schema_version": "epistemic_segment_ordering_v1",
            "ordering_rule": ordering_rule,
            "input_blob_ids": list(normalized_inputs),
            "output_blob_ids": list(output_blob_ids),
        }
    )

    receipt = {
        "schema_version": "epistemic_segment_receipt_v1",
        "segment_receipt_id": "sha256:" + ("0" * 64),
        "episode_id": episode_id,
        "segment_contract_id": segment_contract_id,
        "input_blob_ids": list(normalized_inputs),
        "output_blob_ids": list(output_blob_ids),
        "ordering_hash": ordering_hash,
        "segment_count_u64": int(len(output_blob_ids)),
    }
    receipt["segment_receipt_id"] = canon_hash_obj({k: v for k, v in receipt.items() if k != "segment_receipt_id"})
    receipt_id = str(receipt["segment_receipt_id"])
    receipt_path = outbox_root / "receipts" / "segments" / f"sha256_{receipt_id.split(':', 1)[1]}.epistemic_segment_receipt_v1.json"
    atomic_write_canon_json(receipt_path, receipt)

    return {
        "episode_id": episode_id,
        "segment_contract_id": segment_contract_id,
        "input_blob_ids": list(normalized_inputs),
        "output_blob_ids": list(output_blob_ids),
        "segment_receipt_id": receipt_id,
        "segment_receipt_path": str(receipt_path),
    }


def main() -> None:
    ap = argparse.ArgumentParser(prog="re0_segment_html_live_v1")
    ap.add_argument("--outbox_root", default=".omega_cache/epistemic_outbox")
    ap.add_argument("--episode_id", required=True)
    ap.add_argument("--segment_contract_path", required=True)
    ap.add_argument("--input_blob_id", action="append", required=True)
    args = ap.parse_args()

    out = run(
        outbox_root=Path(args.outbox_root),
        episode_id=str(args.episode_id),
        input_blob_ids=[str(row) for row in list(args.input_blob_id or [])],
        segment_contract_path=Path(args.segment_contract_path),
    )
    print(json.dumps(out, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
