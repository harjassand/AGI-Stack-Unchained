#!/usr/bin/env python3
"""Sealed polymath fetch + immutable blob store helpers (v1)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    _value = str(_entry)
    if _value not in sys.path:
        sys.path.insert(0, _value)

from cdel.v1_7r.canon import canon_bytes, load_canon_json, write_canon_json, write_jsonl_line
from cdel.v18_0.omega_common_v1 import canon_hash_obj, ensure_sha256, validate_schema


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _str_dict(value: Mapping[str, Any] | None) -> dict[str, str]:
    if value is None:
        return {}
    out: dict[str, str] = {}
    for key in sorted(value.keys()):
        out[str(key)] = str(value[key])
    return out


_INDEX_URLS_REL = Path("indexes/urls_to_sha256.jsonl")
_INDEX_DOMAIN_REL = Path("indexes/domain_to_artifacts.jsonl")


def _ensure_store_indexes(store_root: Path) -> None:
    index_root = store_root / "indexes"
    index_root.mkdir(parents=True, exist_ok=True)
    for rel in (_INDEX_URLS_REL, _INDEX_DOMAIN_REL):
        path = store_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text("", encoding="utf-8")


def polymath_store_root(store_root: Path | None) -> Path:
    if store_root is not None:
        resolved = store_root.resolve()
    else:
        env_store_root = str(os.environ.get("OMEGA_POLYMATH_STORE_ROOT", "")).strip()
        if env_store_root:
            resolved = Path(env_store_root).expanduser().resolve()
        else:
            preferred = (_REPO_ROOT / ".omega_cache" / "polymath" / "store").resolve()
            try:
                preferred.mkdir(parents=True, exist_ok=True)
                resolved = preferred
            except OSError:
                resolved = (_REPO_ROOT / "polymath" / "store").resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    _ensure_store_indexes(resolved)
    return resolved


def _store_root(store_root: Path | None) -> Path:
    return polymath_store_root(store_root)


def _blob_path(store_root: Path, digest: str) -> Path:
    ensure_sha256(digest)
    return store_root / "blobs" / "sha256" / digest.split(":", 1)[1]


def _primary_receipt_path(store_root: Path, digest: str) -> Path:
    ensure_sha256(digest)
    return store_root / "receipts" / f"{digest.split(':', 1)[1]}.json"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        payload = json.loads(raw)
        if isinstance(payload, dict):
            out.append(payload)
    return out


def _query_url(url: str, params: Mapping[str, str]) -> str:
    if not params:
        return str(url)
    encoded = urllib.parse.urlencode([(key, params[key]) for key in sorted(params.keys())])
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}{encoded}"


def _request_fingerprint(url: str, headers: Mapping[str, str], params: Mapping[str, str]) -> tuple[dict[str, Any], str]:
    payload = {
        "headers": _str_dict(headers),
        "params": _str_dict(params),
        "url": str(url),
    }
    return payload, "sha256:" + hashlib.sha256(canon_bytes(payload)).hexdigest()


def _normalize_allowed_hosts(values: list[str] | tuple[str, ...] | None) -> set[str] | None:
    if values is None:
        return None
    out = {str(value).strip().lower() for value in values if str(value).strip()}
    if not out:
        return None
    return out


def _assert_allowed_host(*, url: str, allowed_hosts: set[str] | None) -> None:
    if allowed_hosts is None:
        return
    host = str(urllib.parse.urlparse(url).hostname or "").strip().lower()
    if not host or host not in allowed_hosts:
        raise RuntimeError("FORBIDDEN_HOST")


def _net_live_enabled() -> bool:
    return str(os.environ.get("OMEGA_NET_LIVE_OK", "")).strip() == "1"


def _record_url_index(
    *,
    store: Path,
    request_hash: str,
    url: str,
    sha256: str,
    receipt_sha256: str,
) -> None:
    index_path = store / "indexes" / "urls_to_sha256.jsonl"
    row = {
        "fetched_at_utc": _utc_now_iso(),
        "receipt_sha256": receipt_sha256,
        "request_hash": request_hash,
        "schema_version": "polymath_url_index_v1",
        "sha256": sha256,
        "url": str(url),
    }
    write_jsonl_line(index_path, row)


def _record_domain_artifact(
    *,
    store: Path,
    domain_id: str,
    artifact_kind: str,
    sha256: str,
) -> None:
    index_path = store / "indexes" / "domain_to_artifacts.jsonl"
    row = {
        "artifact_kind": str(artifact_kind),
        "created_at_utc": _utc_now_iso(),
        "domain_id": str(domain_id),
        "schema_version": "polymath_domain_artifact_index_v1",
        "sha256": sha256,
    }
    write_jsonl_line(index_path, row)


def _ensure_blob_immutable(path: Path, data: bytes) -> None:
    if path.exists():
        existing = path.read_bytes()
        if hashlib.sha256(existing).hexdigest() != hashlib.sha256(data).hexdigest():
            raise RuntimeError("NONDETERMINISTIC")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _load_receipt(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        payload = load_canon_json(path)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _write_receipt_append_only(path: Path, payload: dict[str, Any]) -> Path:
    existing = _load_receipt(path)
    if existing is None:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_canon_json(path, payload)
        return path
    if canon_hash_obj(existing) == canon_hash_obj(payload):
        return path

    base = path.stem
    suffix = path.suffix
    idx = 1
    while True:
        candidate = path.parent / f"{base}_{idx:04d}{suffix}"
        if candidate.exists():
            existing_alt = _load_receipt(candidate)
            if existing_alt is not None and canon_hash_obj(existing_alt) == canon_hash_obj(payload):
                return candidate
            idx += 1
            continue
        write_canon_json(candidate, payload)
        return candidate


def _lookup_cached_fetch(*, store: Path, request_hash: str) -> tuple[str, Path, Path] | None:
    rows = _read_jsonl(store / "indexes" / "urls_to_sha256.jsonl")
    for row in reversed(rows):
        if str(row.get("request_hash", "")) != request_hash:
            continue
        sha256 = str(row.get("sha256", ""))
        try:
            ensure_sha256(sha256)
        except Exception:
            continue
        blob = _blob_path(store, sha256)
        receipt_sha = str(row.get("receipt_sha256", ""))
        if blob.exists() and blob.is_file():
            if receipt_sha.startswith("sha256:"):
                receipt = _primary_receipt_path(store, sha256)
            else:
                receipt = _primary_receipt_path(store, sha256)
            if receipt.exists() and receipt.is_file():
                return sha256, blob, receipt
    return None


def seal_bytes_with_receipt(
    *,
    data: bytes,
    source_url: str,
    store_root: Path | None = None,
    content_type: str = "application/octet-stream",
    headers: Mapping[str, str] | None = None,
    params: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Seal in-memory bytes into polymath store with a synthetic fetch receipt."""
    store = _store_root(store_root)
    sha256 = "sha256:" + hashlib.sha256(data).hexdigest()
    blob_path = _blob_path(store, sha256)
    _ensure_blob_immutable(blob_path, data)

    request_headers = _str_dict(headers)
    request_params = _str_dict(params)
    receipt_payload = {
        "content_length_u64": int(len(data)),
        "content_type": str(content_type),
        "etag": None,
        "fetched_at_utc": _utc_now_iso(),
        "http_status": 200,
        "last_modified": None,
        "receipt_id": "sha256:" + ("0" * 64),
        "request": {
            "headers": request_headers,
            "params": request_params,
        },
        "schema_version": "polymath_fetch_receipt_v1",
        "sha256": sha256,
        "url": str(source_url),
    }
    no_id = dict(receipt_payload)
    no_id.pop("receipt_id", None)
    receipt_payload["receipt_id"] = canon_hash_obj(no_id)
    validate_schema(receipt_payload, "polymath_fetch_receipt_v1")
    receipt_path = _write_receipt_append_only(_primary_receipt_path(store, sha256), receipt_payload)

    _, request_hash = _request_fingerprint(source_url, request_headers, request_params)
    _record_url_index(
        store=store,
        request_hash=request_hash,
        url=str(source_url),
        sha256=sha256,
        receipt_sha256=str(receipt_payload["receipt_id"]),
    )
    return {
        "bytes_path": blob_path.as_posix(),
        "receipt_path": receipt_path.as_posix(),
        "sha256": sha256,
    }


def fetch_url_sealed(
    url: str,
    headers: Mapping[str, str] | None = None,
    params: Mapping[str, str] | None = None,
    *,
    store_root: Path | None = None,
    timeout_s: int = 45,
    force_refetch: bool = False,
    allowed_hosts: list[str] | tuple[str, ...] | None = None,
    max_bytes: int | None = None,
) -> dict[str, str | bool]:
    """Fetch URL bytes, seal content-addressed blobs, and emit append-only receipts."""
    store = _store_root(store_root)
    request_headers = _str_dict(headers)
    request_params = _str_dict(params)
    requested_url = _query_url(str(url), request_params)
    _assert_allowed_host(url=requested_url, allowed_hosts=_normalize_allowed_hosts(allowed_hosts))
    _, request_hash = _request_fingerprint(requested_url, request_headers, request_params)

    if not force_refetch:
        cached = _lookup_cached_fetch(store=store, request_hash=request_hash)
        if cached is not None:
            sha256, blob_path, receipt_path = cached
            return {
                "bytes_path": blob_path.as_posix(),
                "cached_b": True,
                "receipt_path": receipt_path.as_posix(),
                "sha256": sha256,
                "url": requested_url,
            }
    if not _net_live_enabled():
        raise RuntimeError("NET_DISABLED")

    max_bytes_u64 = None if max_bytes is None else max(1, int(max_bytes))
    request = urllib.request.Request(requested_url, headers=request_headers)
    with urllib.request.urlopen(request, timeout=max(1, int(timeout_s))) as response:
        status = int(getattr(response, "status", 200))
        content_type = str(response.headers.get("Content-Type", ""))
        etag = response.headers.get("ETag")
        last_modified = response.headers.get("Last-Modified")
        if max_bytes_u64 is None:
            data = response.read()
        else:
            header_len = response.headers.get("Content-Length")
            if header_len is not None:
                try:
                    if int(header_len) > int(max_bytes_u64):
                        raise RuntimeError("FETCH_TOO_LARGE")
                except ValueError:
                    pass
            remaining = int(max_bytes_u64) + 1
            chunks: list[bytes] = []
            while remaining > 0:
                chunk = response.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            data = b"".join(chunks)
            if len(data) > int(max_bytes_u64):
                raise RuntimeError("FETCH_TOO_LARGE")

    sha256 = "sha256:" + hashlib.sha256(data).hexdigest()
    blob_path = _blob_path(store, sha256)
    _ensure_blob_immutable(blob_path, data)

    receipt_payload = {
        "content_length_u64": int(len(data)),
        "content_type": content_type,
        "etag": etag,
        "fetched_at_utc": _utc_now_iso(),
        "http_status": status,
        "last_modified": last_modified,
        "receipt_id": "sha256:" + ("0" * 64),
        "request": {
            "headers": request_headers,
            "params": request_params,
        },
        "schema_version": "polymath_fetch_receipt_v1",
        "sha256": sha256,
        "url": requested_url,
    }
    no_id = dict(receipt_payload)
    no_id.pop("receipt_id", None)
    receipt_payload["receipt_id"] = canon_hash_obj(no_id)
    validate_schema(receipt_payload, "polymath_fetch_receipt_v1")
    receipt_path = _write_receipt_append_only(_primary_receipt_path(store, sha256), receipt_payload)

    _record_url_index(
        store=store,
        request_hash=request_hash,
        url=requested_url,
        sha256=sha256,
        receipt_sha256=str(receipt_payload["receipt_id"]),
    )
    return {
        "bytes_path": blob_path.as_posix(),
        "cached_b": False,
        "receipt_path": receipt_path.as_posix(),
        "sha256": sha256,
        "url": requested_url,
    }


def load_blob_bytes(*, sha256: str, store_root: Path | None = None) -> bytes:
    store = _store_root(store_root)
    path = _blob_path(store, sha256)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(path)
    data = path.read_bytes()
    digest = "sha256:" + hashlib.sha256(data).hexdigest()
    if digest != sha256:
        raise RuntimeError("NONDETERMINISTIC")
    return data


def record_domain_artifact(*, domain_id: str, artifact_kind: str, sha256: str, store_root: Path | None = None) -> None:
    _record_domain_artifact(
        store=_store_root(store_root),
        domain_id=domain_id,
        artifact_kind=artifact_kind,
        sha256=sha256,
    )


def _parse_headers(values: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for value in values:
        if ":" not in value:
            raise ValueError(f"invalid header (expected K:V): {value}")
        key, raw_value = value.split(":", 1)
        out[key.strip()] = raw_value.strip()
    return out


def _parse_params(values: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"invalid param (expected k=v): {value}")
        key, raw_value = value.split("=", 1)
        out[key.strip()] = raw_value.strip()
    return out


def main() -> None:
    parser = argparse.ArgumentParser(prog="polymath_dataset_fetch_v1")
    parser.add_argument("--url", required=True)
    parser.add_argument("--header", action="append", default=[])
    parser.add_argument("--param", action="append", default=[])
    parser.add_argument("--store_root", default="")
    parser.add_argument("--timeout_s", type=int, default=45)
    parser.add_argument("--force_refetch", type=int, default=0)
    parser.add_argument("--allowed_host", action="append", default=[])
    parser.add_argument("--max_bytes", type=int, default=0)
    args = parser.parse_args()

    headers = _parse_headers([str(x) for x in args.header])
    params = _parse_params([str(x) for x in args.param])
    store_root = Path(args.store_root).resolve() if str(args.store_root).strip() else None
    result = fetch_url_sealed(
        str(args.url),
        headers=headers,
        params=params,
        store_root=store_root,
        timeout_s=max(1, int(args.timeout_s)),
        force_refetch=bool(int(args.force_refetch)),
        allowed_hosts=[str(value).strip() for value in args.allowed_host if str(value).strip()] or None,
        max_bytes=(max(1, int(args.max_bytes)) if int(args.max_bytes) > 0 else None),
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
