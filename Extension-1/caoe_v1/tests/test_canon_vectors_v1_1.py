from __future__ import annotations

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from api_v1 import canonical_json_bytes  # noqa: E402
from artifacts.ids_v1 import sha256_hex  # noqa: E402


def _find_vectors_path() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "Genesis" / "extensions" / "caoe_v1_1" / "VECTORS" / "canon_vectors_v1.json"
        if candidate.exists():
            return candidate
    raise RuntimeError("canon_vectors_v1.json not found")


def test_canon_vectors_v1_1() -> None:
    vectors_path = _find_vectors_path()
    payload = json.loads(vectors_path.read_text(encoding="utf-8"))
    vectors = payload.get("vectors") or []
    for vec in vectors:
        name = vec.get("name")
        obj = vec.get("object")
        expected = vec.get("canon_sha256")
        actual = sha256_hex(canonical_json_bytes(obj))
        assert actual == expected, f"canon vector mismatch: {name}"
