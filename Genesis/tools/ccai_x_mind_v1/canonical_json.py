import sys
from decimal import Decimal
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(TOOLS_DIR))
import canonicalize as canon  # noqa: E402


def assert_no_floats(obj, path="$") -> None:
    if isinstance(obj, bool) or obj is None:
        return
    if isinstance(obj, float):
        raise ValueError(f"float not allowed at {path}")
    if isinstance(obj, Decimal):
        if obj.as_tuple().exponent != 0:
            raise ValueError(f"non-integer decimal not allowed at {path}")
        return
    if isinstance(obj, int):
        return
    if isinstance(obj, str):
        return
    if isinstance(obj, list):
        for idx, item in enumerate(obj):
            assert_no_floats(item, f"{path}[{idx}]")
        return
    if isinstance(obj, dict):
        for key, value in obj.items():
            assert_no_floats(value, f"{path}.{key}")
        return
    raise ValueError(f"unsupported type at {path}: {type(obj)}")


def _to_decimal(obj):
    if isinstance(obj, bool) or obj is None:
        return obj
    if isinstance(obj, Decimal):
        return obj
    if isinstance(obj, int):
        return Decimal(obj)
    if isinstance(obj, str):
        return obj
    if isinstance(obj, list):
        return [_to_decimal(item) for item in obj]
    if isinstance(obj, dict):
        return {key: _to_decimal(value) for key, value in obj.items()}
    raise ValueError(f"unsupported type for canonicalization: {type(obj)}")


def to_gcj1_bytes(obj) -> bytes:
    assert_no_floats(obj)
    return canon.canonical_bytes(_to_decimal(obj))
