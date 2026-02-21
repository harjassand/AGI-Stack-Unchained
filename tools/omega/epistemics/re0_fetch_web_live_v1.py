"""RE0 LIVE_WEB ingestion with deterministic fixture-backed mode."""

from __future__ import annotations

import argparse
import json
import os
import urllib.request
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


def _load_fetch_contract(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("SCHEMA_FAIL")
    if str(payload.get("schema_version", "")).strip() != "epistemic_fetch_contract_v1":
        raise RuntimeError("SCHEMA_FAIL")
    fetch_contract_id = ensure_sha256(payload.get("fetch_contract_id"))
    no_id = dict(payload)
    no_id.pop("fetch_contract_id", None)
    if canon_hash_obj(no_id) != fetch_contract_id:
        raise RuntimeError("NONDETERMINISTIC")
    nonce_mode = str(payload.get("nonce_mode", "")).strip().upper()
    if nonce_mode not in {"DETERMINISTIC_FROM_BYTES", "RANDOM_OK"}:
        raise RuntimeError("SCHEMA_FAIL")
    timeout_ms_u32 = int(payload.get("timeout_ms_u32", 0))
    if timeout_ms_u32 <= 0:
        raise RuntimeError("SCHEMA_FAIL")
    header_allowlist = payload.get("header_allowlist")
    if not isinstance(header_allowlist, list):
        raise RuntimeError("SCHEMA_FAIL")
    payload["nonce_mode"] = nonce_mode
    return payload


def _fetch_live(*, url: str, timeout_ms_u32: int, user_agent: str) -> tuple[int, bytes, dict[str, str]]:
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=float(timeout_ms_u32) / 1000.0) as resp:
        status = int(getattr(resp, "status", 200))
        body = resp.read()
        headers = {str(k): str(v) for k, v in resp.headers.items()}
    return status, body, headers


def _select_headers(*, headers: dict[str, str], allowlist: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    lower = {str(k).lower(): str(v) for k, v in headers.items()}
    for key in sorted(str(row).strip().lower() for row in allowlist if str(row).strip()):
        if key in lower:
            out[key] = lower[key]
    return out


def run(
    *,
    url: str,
    outbox_root: Path,
    episode_id: str,
    fetch_contract_path: Path,
    fixture_body_path: Path | None = None,
    fixture_headers_path: Path | None = None,
    fixture_status_code: int | None = None,
) -> dict[str, Any]:
    outbox_root = outbox_root.resolve()
    episode_id = ensure_sha256(episode_id)
    fetch_contract = _load_fetch_contract(fetch_contract_path.resolve())
    fetch_contract_id = ensure_sha256(fetch_contract.get("fetch_contract_id"))

    if fixture_body_path is not None:
        body = fixture_body_path.resolve().read_bytes()
        status = int(200 if fixture_status_code is None else fixture_status_code)
        headers: dict[str, str] = {}
        if fixture_headers_path is not None:
            headers_payload = json.loads(fixture_headers_path.resolve().read_text(encoding="utf-8"))
            if not isinstance(headers_payload, dict):
                raise RuntimeError("SCHEMA_FAIL")
            headers = {str(k): str(v) for k, v in headers_payload.items()}
    else:
        user_agent = str(fetch_contract.get("user_agent", "AGI-Stack-Unchained/epistemic-re0"))
        status, body, headers = _fetch_live(
            url=str(url),
            timeout_ms_u32=int(fetch_contract.get("timeout_ms_u32", 1000)),
            user_agent=user_agent,
        )

    raw_blob_id = hash_bytes(body)
    raw_blob_path = outbox_root / "blobs" / "sha256" / raw_blob_id.split(":", 1)[1]
    if raw_blob_path.exists():
        if hash_bytes(raw_blob_path.read_bytes()) != raw_blob_id:
            raise RuntimeError("HASH_MISMATCH")
    else:
        atomic_write_bytes(raw_blob_path, body)

    nonce_mode = str(fetch_contract.get("nonce_mode", "DETERMINISTIC_FROM_BYTES")).upper()
    if nonce_mode == "DETERMINISTIC_FROM_BYTES":
        capture_nonce_u64 = deterministic_nonce_u64(
            source_uri=str(url),
            raw_blob_id=raw_blob_id,
            fetch_contract_id=fetch_contract_id,
        )
    else:
        capture_nonce_u64 = int.from_bytes(os.urandom(8), "big", signed=False)

    selected_headers = _select_headers(
        headers=headers,
        allowlist=[str(row) for row in list(fetch_contract.get("header_allowlist") or [])],
    )
    receipt = {
        "schema_version": "epistemic_fetch_receipt_v1",
        "fetch_receipt_id": "sha256:" + ("0" * 64),
        "episode_id": episode_id,
        "source_uri": str(url),
        "status_code_u16": int(status),
        "selected_headers": selected_headers,
        "raw_blob_id": raw_blob_id,
        "capture_nonce_u64": int(capture_nonce_u64),
        "fetch_contract_id": fetch_contract_id,
    }
    receipt["fetch_receipt_id"] = canon_hash_obj({k: v for k, v in receipt.items() if k != "fetch_receipt_id"})
    receipt_id = str(receipt["fetch_receipt_id"])
    receipt_path = outbox_root / "receipts" / "fetch" / f"sha256_{receipt_id.split(':', 1)[1]}.epistemic_fetch_receipt_v1.json"
    atomic_write_canon_json(receipt_path, receipt)

    return {
        "episode_id": episode_id,
        "fetch_contract_id": fetch_contract_id,
        "raw_blob_id": raw_blob_id,
        "fetch_receipt_id": receipt_id,
        "fetch_receipt_path": str(receipt_path),
        "nonce_mode": nonce_mode,
    }


def main() -> None:
    ap = argparse.ArgumentParser(prog="re0_fetch_web_live_v1")
    ap.add_argument("--url", required=True)
    ap.add_argument("--outbox_root", default=".omega_cache/epistemic_outbox")
    ap.add_argument("--episode_id", required=True)
    ap.add_argument("--fetch_contract_path", required=True)
    ap.add_argument("--fixture_body_path")
    ap.add_argument("--fixture_headers_path")
    ap.add_argument("--fixture_status_code", type=int)
    args = ap.parse_args()
    out = run(
        url=str(args.url),
        outbox_root=Path(args.outbox_root),
        episode_id=str(args.episode_id),
        fetch_contract_path=Path(args.fetch_contract_path),
        fixture_body_path=(Path(args.fixture_body_path) if args.fixture_body_path else None),
        fixture_headers_path=(Path(args.fixture_headers_path) if args.fixture_headers_path else None),
        fixture_status_code=(int(args.fixture_status_code) if args.fixture_status_code is not None else None),
    )
    print(json.dumps(out, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
