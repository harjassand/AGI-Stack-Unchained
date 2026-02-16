"""GCJ-1 canonical JSON + hashing helpers for EUDRS-U v1.

Phase-1 determinism substrate rules (normative):
  - JSON is UTF-8, GCJ-1 canonical (sorted keys, separators (",", ":"), trailing newline).
  - Floats are rejected at load time (including exponent notation).
  - Artifact IDs are sha256 over canonical bytes:
      * JSON: sha256(canonical_json_bytes_with_trailing_newline)
      * BIN:  sha256(raw_bytes)

This module is RE2: deterministic and fail-closed.
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

from ..omega_common_v1 import fail


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_prefixed(data: bytes) -> str:
    return f"sha256:{sha256_hex(data)}"


def sha256_file_stream(path: Path, *, chunk_size: int = 4 * 1024 * 1024) -> str:
    if not path.exists() or not path.is_file():
        fail("MISSING_STATE_INPUT")
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return f"sha256:{hasher.hexdigest()}"

class _RejectFloat(ValueError):
    pass


def _reject_float(_value: str) -> Any:
    raise _RejectFloat("floats are forbidden in GCJ-1 JSON")


def _reject_constant(_value: str) -> Any:
    # Covers NaN / Infinity / -Infinity.
    raise _RejectFloat("float-like constants are forbidden in GCJ-1 JSON")


def _validate_gcj1_obj(value: Any) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                fail("SCHEMA_FAIL")
            _validate_gcj1_obj(v)
        return
    if isinstance(value, list):
        for item in value:
            _validate_gcj1_obj(item)
        return
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        fail("SCHEMA_FAIL")
    fail("SCHEMA_FAIL")


def gcj1_loads_strict(raw: bytes | str) -> Any:
    """Strict JSON loader: UTF-8 + float rejection + type enforcement."""

    if isinstance(raw, (bytes, bytearray, memoryview)):
        try:
            text = bytes(raw).decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            fail("SCHEMA_FAIL")
    elif isinstance(raw, str):
        text = raw
    else:
        fail("SCHEMA_FAIL")

    try:
        obj = json.loads(
            text,
            parse_int=int,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except _RejectFloat:
        fail("SCHEMA_FAIL")
    except Exception:
        fail("SCHEMA_FAIL")

    _validate_gcj1_obj(obj)
    return obj


def gcj1_canon_bytes(obj: Any) -> bytes:
    """Return GCJ-1 canonical JSON bytes (including the trailing newline)."""

    _validate_gcj1_obj(obj)
    try:
        body = json.dumps(
            obj,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8", errors="strict")
    except Exception:
        fail("SCHEMA_FAIL")
    return body + b"\n"


def gcj1_loads_and_verify_canonical(raw_bytes: bytes) -> Any:
    """Parse strict GCJ-1 JSON and require bytes on disk are exactly canonical."""

    if not isinstance(raw_bytes, (bytes, bytearray, memoryview)):
        fail("SCHEMA_FAIL")
    raw = bytes(raw_bytes)
    obj = gcj1_loads_strict(raw)
    canon = gcj1_canon_bytes(obj)
    if raw != canon:
        fail("SCHEMA_FAIL")
    return obj


def artifact_id_from_json_bytes(raw_bytes: bytes) -> str:
    """Compute sha256:<hex> for a JSON artifact (requires canonical bytes)."""

    gcj1_loads_and_verify_canonical(raw_bytes)
    return sha256_prefixed(bytes(raw_bytes))


def artifact_id_from_json_obj(obj: Any) -> str:
    """Compute sha256:<hex> for a JSON object in GCJ-1 canonical form."""

    return sha256_prefixed(gcj1_canon_bytes(obj))


def artifact_id_from_bin_bytes(raw_bytes: bytes) -> str:
    return sha256_prefixed(bytes(raw_bytes))


def load_gcj1_canon_json(path: Path) -> Any:
    """Load a JSON artifact from disk and verify it is GCJ-1 canonical bytes."""

    if not isinstance(path, Path):
        path = Path(path)
    if not path.exists() or not path.is_file():
        fail("MISSING_STATE_INPUT")
    return gcj1_loads_and_verify_canonical(path.read_bytes())


__all__ = [
    "artifact_id_from_bin_bytes",
    "artifact_id_from_json_bytes",
    "artifact_id_from_json_obj",
    "gcj1_canon_bytes",
    "gcj1_loads_and_verify_canonical",
    "gcj1_loads_strict",
    "load_gcj1_canon_json",
    "sha256_file_stream",
    "sha256_hex",
    "sha256_prefixed",
]
