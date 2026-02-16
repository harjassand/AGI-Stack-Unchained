import json
import sys
import unittest
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"jsonschema not available: {exc}")

ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / "tools"
VEC_DIR = ROOT / "test_vectors" / "ccai_x_mind_v2"
SCHEMA_DIR = ROOT / "schema" / "ccai_x_mind_v2"

sys.path.insert(0, str(TOOLS_DIR))

from ccai_x_mind_v1.canonical_json import assert_no_floats, to_gcj1_bytes  # noqa: E402
from ccai_x_mind_v1.validate_instance import validate_path  # noqa: E402


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _schema_validator(schema_path: Path) -> Draft202012Validator:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


class TestCcaiXMindV2Vectors(unittest.TestCase):
    def test_validate_instances(self) -> None:
        validate_path(VEC_DIR / "base_registry.json")
        validate_path(VEC_DIR / "target_registry.json")

        diff = _load_json(VEC_DIR / "mechanism_registry_diff.json")
        assert_no_floats(diff)
        schema = _schema_validator(SCHEMA_DIR / "mechanism_registry_diff_v1.schema.json")
        errors = sorted(schema.iter_errors(diff), key=lambda e: e.path)
        if errors:
            err = errors[0]
            loc = "/".join(str(p) for p in err.path)
            raise AssertionError(f"schema error at {loc or '<root>'}: {err.message}")

        # Ensure canonical JSON bytes match fixture.
        raw = (VEC_DIR / "mechanism_registry_diff.json").read_bytes()
        if raw.endswith(b"\n"):
            raw = raw[:-1]
        self.assertEqual(to_gcj1_bytes(diff), raw)

    def test_base_hash_matches(self) -> None:
        base = _load_json(VEC_DIR / "base_registry.json")
        diff = _load_json(VEC_DIR / "mechanism_registry_diff.json")
        base_hash = _sha256_hex(to_gcj1_bytes(base))
        self.assertEqual(diff.get("base_registry_hash"), base_hash)


def _sha256_hex(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


if __name__ == "__main__":
    raise SystemExit(unittest.main())
