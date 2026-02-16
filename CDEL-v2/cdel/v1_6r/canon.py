"""GCJ-1 canonicalization and hashing utilities for v1.5r."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class CanonError(ValueError):
    """Raised when canonical JSON constraints are violated."""


def _reject_float(value: str) -> Any:
    raise CanonError("floats are not allowed in canonical json")


def loads(raw: bytes | str) -> Any:
    """Parse JSON and reject floats or invalid UTF-8."""
    if isinstance(raw, bytes):
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CanonError("json must be utf-8") from exc
    else:
        text = raw
    try:
        return json.loads(text, parse_int=int, parse_float=_reject_float)
    except CanonError:
        raise
    except Exception as exc:  # noqa: BLE001 - normalize parse errors
        raise CanonError("invalid json") from exc


def load(path: str | Path) -> Any:
    path = Path(path)
    return loads(path.read_bytes())


def _validate(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonError("canonical json keys must be strings")
            _validate(item)
        return
    if isinstance(value, list):
        for item in value:
            _validate(item)
        return
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        raise CanonError("floats are not allowed in canonical json")
    raise CanonError("unsupported json type in canonical json")


def canon_bytes(payload: Any) -> bytes:
    """Return GCJ-1 canonical bytes for JSON data."""
    _validate(payload)
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_prefixed(data: bytes) -> str:
    return f"sha256:{sha256_hex(data)}"


def hash_json(payload: Any) -> str:
    return sha256_prefixed(canon_bytes(payload))


def load_canon_json(path: str | Path) -> Any:
    """Load JSON and ensure it is GCJ-1 canonical on disk."""
    path = Path(path)
    raw = path.read_bytes()
    payload = loads(raw)
    canon = canon_bytes(payload)
    raw_norm = raw.rstrip(b"\n")
    if raw_norm != canon:
        raise CanonError(f"non-canonical JSON: {path}")
    return payload


def write_canon_json(path: str | Path, payload: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canon_bytes(payload) + b"\n")


def write_jsonl_line(path: str | Path, payload: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        handle.write(canon_bytes(payload) + b"\n")
