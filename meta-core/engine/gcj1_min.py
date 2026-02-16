import json
from typing import Any


def _encode_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _encode_value(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        raise ValueError("floats are not permitted in GCJ-1-min encoding")
    if isinstance(value, str):
        return _encode_string(value)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_encode_value(v) for v in value) + "]"
    if isinstance(value, dict):
        items = []
        for key in sorted(value.keys()):
            if not isinstance(key, str):
                raise ValueError("object keys must be strings for GCJ-1-min encoding")
            items.append(_encode_string(key) + ":" + _encode_value(value[key]))
        return "{" + ",".join(items) + "}"
    raise ValueError(f"unsupported type for GCJ-1-min encoding: {type(value)!r}")


def dumps(obj: Any) -> str:
    return _encode_value(obj)


def dumps_bytes(obj: Any) -> bytes:
    return dumps(obj).encode("utf-8")
