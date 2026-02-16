"""JSON canonicalization for signed sealed payloads (JCS-compatible subset)."""

from __future__ import annotations

import json
from typing import Any


def canon_bytes(payload: Any) -> bytes:
    _validate(payload)
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _validate(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("canonical json keys must be strings")
            _validate(item)
        return
    if isinstance(value, list):
        for item in value:
            _validate(item)
        return
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        raise ValueError("floats are not allowed in signed payloads")
    raise ValueError("unsupported json type in signed payloads")
