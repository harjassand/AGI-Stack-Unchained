import json
from pathlib import Path

from cdel.kernel import canon


def _load_payload(name: str) -> dict:
    data = json.loads(Path(name).read_text(encoding="utf-8"))
    return data["payload"]


def test_hash_changes_on_semantic_change():
    payload_a = _load_payload("tests/fixtures/module_a.json")
    payload_c = _load_payload("tests/fixtures/module_c.json")

    hash_a = canon.payload_hash_hex(canon.canonicalize_payload(payload_a))
    hash_c = canon.payload_hash_hex(canon.canonicalize_payload(payload_c))

    assert hash_a != hash_c
