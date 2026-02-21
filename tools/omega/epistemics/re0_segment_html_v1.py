"""Deterministic HTML segmenter for RE0 epistemic outbox."""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

try:
    from .common_v1 import atomic_write_canon_json, canon_hash_obj, ensure_sha256, hash_file
except Exception:  # pragma: no cover
    from common_v1 import atomic_write_canon_json, canon_hash_obj, ensure_sha256, hash_file

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\n]+")


def _validate_segment_contract(path: Path) -> dict[str, object]:
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
    impl_path = Path(impl_rel)
    if not impl_rel or impl_path.is_absolute() or ".." in impl_path.parts:
        raise RuntimeError("SCHEMA_FAIL")
    impl_abs = (Path.cwd() / impl_path).resolve()
    if not impl_abs.exists() or not impl_abs.is_file():
        raise RuntimeError("MISSING_INPUT")
    if hash_file(impl_abs) != ensure_sha256(payload.get("segmenter_impl_sha256")):
        raise RuntimeError("PIN_HASH_MISMATCH")
    return payload


def _strip_html(raw_bytes: bytes) -> str:
    text = raw_bytes.decode("utf-8", errors="replace")
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = _WS_RE.sub(" ", text)
    return text.strip()


def _segment(text: str, *, max_segment_len: int) -> list[str]:
    if not text:
        return []
    parts = [chunk.strip() for chunk in re.split(r"(?<=[.!?])\s+", text) if chunk.strip()]
    out: list[str] = []
    for chunk in parts:
        while len(chunk) > max_segment_len:
            out.append(chunk[:max_segment_len])
            chunk = chunk[max_segment_len:]
        if chunk:
            out.append(chunk)
    return out


def run(
    *,
    raw_blob_path: Path,
    out_path: Path,
    max_segment_len: int,
    segment_contract_path: Path | None = None,
) -> dict[str, object]:
    if segment_contract_path is not None:
        contract = _validate_segment_contract(segment_contract_path.resolve())
        max_segment_len = int(contract.get("max_segment_len_u32", max_segment_len))
    raw = raw_blob_path.read_bytes()
    text = _strip_html(raw)
    segments = _segment(text, max_segment_len=max_segment_len)
    payload = {
        "schema_version": "epistemic_segment_output_v1",
        "segmenter_id": "HTML_READER_SEGMENT_V1",
        "raw_blob_id": "sha256:" + raw_blob_path.name,
        "segments": segments,
    }
    payload["segment_output_id"] = canon_hash_obj({k: v for k, v in payload.items() if k != "segment_output_id"})
    atomic_write_canon_json(out_path, payload)
    return payload


def main() -> None:
    ap = argparse.ArgumentParser(prog="re0_segment_html_v1")
    ap.add_argument("--raw_blob_path", required=True)
    ap.add_argument("--out_path", required=True)
    ap.add_argument("--max_segment_len", type=int, default=2048)
    ap.add_argument("--segment_contract_path")
    args = ap.parse_args()
    payload = run(
        raw_blob_path=Path(args.raw_blob_path).resolve(),
        out_path=Path(args.out_path).resolve(),
        max_segment_len=max(1, int(args.max_segment_len)),
        segment_contract_path=(Path(args.segment_contract_path) if args.segment_contract_path else None),
    )
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
