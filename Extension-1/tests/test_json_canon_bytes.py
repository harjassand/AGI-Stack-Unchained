import pytest

from self_improve_code_v1.canon.json_canon_v1 import canon_bytes


def test_canon_bytes_sorted_and_compact():
    obj = {"b": 2, "a": 1}
    out = canon_bytes(obj).decode("utf-8")
    assert out == '{"a":1,"b":2}'


def test_canon_bytes_rejects_float():
    with pytest.raises(ValueError):
        canon_bytes({"a": 1.2})
