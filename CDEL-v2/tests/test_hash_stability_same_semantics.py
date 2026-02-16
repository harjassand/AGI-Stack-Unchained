import json
from pathlib import Path

from cdel.kernel import canon


def _load_payload(name: str) -> dict:
    data = json.loads(Path(name).read_text(encoding="utf-8"))
    return data["payload"]


def test_hash_stability_same_semantics():
    payload_a = _load_payload("tests/fixtures/module_a.json")
    payload_b = _load_payload("tests/fixtures/module_b.json")

    canon_a = canon.canonicalize_payload(payload_a)
    canon_b = canon.canonicalize_payload(payload_b)

    assert canon_a == canon_b
    assert canon.payload_hash_hex(canon_a) == canon.payload_hash_hex(canon_b)
