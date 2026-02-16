"""Canonical JSON serialization (v1)."""

from __future__ import annotations

import json
from typing import Any


def _assert_ints_only(obj: Any, path: str = "$") -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, int):
        return
    if isinstance(obj, float):
        raise ValueError(f"float not allowed at {path}")
    if obj is None:
        return
    if isinstance(obj, str):
        return
    if isinstance(obj, (list, tuple)):
        for i, item in enumerate(obj):
            _assert_ints_only(item, f"{path}[{i}]")
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                raise ValueError(f"non-string key at {path}")
            _assert_ints_only(v, f"{path}.{k}")
        return
    raise ValueError(f"unsupported type at {path}: {type(obj).__name__}")


def canon_dumps(obj: Any) -> str:
    _assert_ints_only(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canon_bytes(obj: Any) -> bytes:
    return canon_dumps(obj).encode("utf-8")


__all__ = ["canon_dumps", "canon_bytes"]
