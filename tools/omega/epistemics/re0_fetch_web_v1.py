"""RE0 web fetch tool for epistemic outbox ingestion."""

from __future__ import annotations

import argparse
import json
import os
import urllib.request
from pathlib import Path

try:
    from .common_v1 import atomic_write_bytes, canon_hash_obj, hash_bytes
except Exception:  # pragma: no cover
    from common_v1 import atomic_write_bytes, canon_hash_obj, hash_bytes


def _fetch_bytes(url: str, *, timeout_s: float, user_agent: str) -> tuple[int, bytes, dict[str, str]]:
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        status = int(getattr(resp, "status", 200))
        body = resp.read()
        headers = {str(k): str(v) for k, v in resp.headers.items()}
    return status, body, headers


def run(*, url: str, outbox_root: Path, timeout_s: float, user_agent: str) -> dict[str, object]:
    status, body, headers = _fetch_bytes(url, timeout_s=timeout_s, user_agent=user_agent)
    raw_blob_id = hash_bytes(body)
    digest = raw_blob_id.split(":", 1)[1]
    blob_path = outbox_root / "blobs" / "sha256" / digest
    if blob_path.exists():
        existing = blob_path.read_bytes()
        if hash_bytes(existing) != raw_blob_id:
            raise RuntimeError("HASH_MISMATCH")
    else:
        atomic_write_bytes(blob_path, body)

    receipt = {
        "schema_version": "epistemic_fetch_receipt_v1",
        "url": str(url),
        "status_code_u16": int(status),
        "selected_headers": {
            "content-type": headers.get("Content-Type", ""),
            "etag": headers.get("ETag", ""),
            "last-modified": headers.get("Last-Modified", ""),
        },
        "raw_blob_id": raw_blob_id,
        "capture_nonce_u64": int(os.environ.get("OMEGA_TICK_U64", "0") or "0"),
    }
    receipt["receipt_id"] = canon_hash_obj({k: v for k, v in receipt.items() if k != "receipt_id"})
    return receipt


def main() -> None:
    ap = argparse.ArgumentParser(prog="re0_fetch_web_v1")
    ap.add_argument("--url", required=True)
    ap.add_argument("--outbox_root", default=".omega_cache/epistemic_outbox")
    ap.add_argument("--timeout_s", type=float, default=20.0)
    ap.add_argument("--user_agent", default="AGI-Stack-Unchained/epistemic-re0")
    args = ap.parse_args()
    out = run(
        url=str(args.url),
        outbox_root=Path(args.outbox_root).resolve(),
        timeout_s=float(args.timeout_s),
        user_agent=str(args.user_agent),
    )
    print(json.dumps(out, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
