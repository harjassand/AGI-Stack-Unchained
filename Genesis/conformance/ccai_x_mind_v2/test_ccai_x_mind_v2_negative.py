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

from ccai_x_mind_v1.canonical_json import assert_no_floats  # noqa: E402


def _schema_validator(schema_path: Path) -> Draft202012Validator:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


class TestCcaiXMindV2Negative(unittest.TestCase):
    def test_invalid_diff_rejected(self) -> None:
        diff = json.loads((VEC_DIR / "mechanism_registry_diff_invalid.json").read_text(encoding="utf-8"))
        assert_no_floats(diff)
        schema = _schema_validator(SCHEMA_DIR / "mechanism_registry_diff_v1.schema.json")
        errors = list(schema.iter_errors(diff))
        self.assertTrue(errors, "expected schema validation errors")


if __name__ == "__main__":
    raise SystemExit(unittest.main())
