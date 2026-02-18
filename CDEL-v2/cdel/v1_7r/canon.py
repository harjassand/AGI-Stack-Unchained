"""GCJ-1 canonicalization and hashing utilities for v1.7r."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Any


class CanonError(ValueError):
    """Raised when canonical JSON constraints are violated."""

_NATIVE_CANON_ENV = "OMEGA_NATIVE_CANON_BYTES"
_NATIVE_CANON_OP_ID = "omega_kernel_canon_bytes_v1"
_TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}
_tls = threading.local()


@contextlib.contextmanager
def native_canon_disabled():
    """Force pure-Python canonicalization within this context."""

    prev = bool(getattr(_tls, "native_disabled", False))
    _tls.native_disabled = True
    try:
        yield
    finally:
        _tls.native_disabled = prev


def _native_canon_allowed() -> bool:
    if bool(getattr(_tls, "native_disabled", False)):
        return False
    raw = str(os.environ.get(_NATIVE_CANON_ENV, "")).strip().lower()
    return raw in _TRUTHY_ENV_VALUES


def _repo_root() -> Path:
    # .../repo_root/CDEL-v2/cdel/v1_7r/canon.py
    return Path(__file__).resolve().parents[3]


_ACTIVE_REGISTRY_CACHE: dict[str, Any] = {"mtime_ns": None, "payload": None}
_DISABLED_CACHE: dict[str, Any] = {"mtime_ns": None, "payload": None}


def _load_json_cached(path: Path, cache: dict[str, Any]) -> dict[str, Any]:
    try:
        stat = path.stat()
    except FileNotFoundError:
        cache["mtime_ns"] = None
        cache["payload"] = None
        return {}
    except Exception:
        cache["mtime_ns"] = None
        cache["payload"] = None
        return {}
    mtime_ns = int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1e9)))
    if cache.get("mtime_ns") == mtime_ns and isinstance(cache.get("payload"), dict):
        return cache["payload"]
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    payload = raw if isinstance(raw, dict) else {}
    cache["mtime_ns"] = mtime_ns
    cache["payload"] = payload
    return payload


def _active_binary_for_op(op_id: str) -> str | None:
    reg_path = _repo_root() / ".omega_cache" / "native_runtime" / "active_registry_v1.json"
    payload = _load_json_cached(reg_path, _ACTIVE_REGISTRY_CACHE)
    mapping = payload.get("ops")
    if not isinstance(mapping, dict):
        return None
    row = mapping.get(op_id)
    if not isinstance(row, dict):
        return None
    val = row.get("binary_sha256")
    if isinstance(val, str) and val.startswith("sha256:") and len(val) == 71:
        return val
    return None


def _is_disabled(op_id: str, binary_sha256: str) -> bool:
    dis_path = _repo_root() / ".omega_cache" / "native_runtime" / "disabled_v1.json"
    payload = _load_json_cached(dis_path, _DISABLED_CACHE)
    disabled = payload.get("disabled")
    if not isinstance(disabled, dict):
        return False
    key = f"{op_id}|{binary_sha256}"
    return bool(disabled.get(key))


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


def _canon_bytes_validated(payload: Any, *, sort_keys: bool) -> bytes:
    # The python `json` module already emits integers without leading zeros.
    return json.dumps(
        payload,
        sort_keys=bool(sort_keys),
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canon_bytes_pure(payload: Any) -> bytes:
    """Return GCJ-1 canonical bytes for JSON data (pure python baseline)."""

    _validate(payload)
    return _canon_bytes_validated(payload, sort_keys=True)


def canon_bytes(payload: Any) -> bytes:
    """Return GCJ-1 canonical bytes for JSON data.

    When `OMEGA_NATIVE_CANON_BYTES=1` and a native module is active for
    `omega_kernel_canon_bytes_v1`, this function will opportunistically route
    through the native pipeline. Fallback is always the pure-python baseline.
    """

    _validate(payload)
    if not _native_canon_allowed():
        return _canon_bytes_validated(payload, sort_keys=True)

    active_bin = _active_binary_for_op(_NATIVE_CANON_OP_ID)
    if not active_bin or _is_disabled(_NATIVE_CANON_OP_ID, active_bin):
        return _canon_bytes_validated(payload, sort_keys=True)

    # Encode without sorting; native canonicalization will sort deterministically.
    raw = _canon_bytes_validated(payload, sort_keys=False)
    try:
        from orchestrator.native import native_router_v1
    except Exception:
        return _canon_bytes_validated(payload, sort_keys=True)
    try:
        out = native_router_v1.route(_NATIVE_CANON_OP_ID, raw)
        if isinstance(out, (bytes, bytearray, memoryview)):
            return bytes(out)
    except Exception:
        # Runtime fallback must remain safe and deterministic.
        return _canon_bytes_validated(payload, sort_keys=True)
    return _canon_bytes_validated(payload, sort_keys=True)


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
    # Disk canonicality checks must remain independent of any native acceleration.
    canon = canon_bytes_pure(payload)
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
