from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "capsules" / "schema"
CAPSULE_SCHEMA_PATH = SCHEMA_DIR / "capsule.schema.json"
RECEIPT_SCHEMA_PATH = SCHEMA_DIR / "receipt.schema.json"


def _load_schema(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def validate_capsule(capsule: dict) -> tuple[bool, str | None]:
    schema = _load_schema(CAPSULE_SCHEMA_PATH)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(capsule), key=lambda e: e.path)
    if errors:
        err = errors[0]
        loc = "/".join(str(p) for p in err.path) or "<root>"
        return False, f"{loc}: {err.message}"
    return True, None


def validate_receipt(receipt: dict) -> tuple[bool, str | None]:
    schema = _load_schema(RECEIPT_SCHEMA_PATH)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(receipt), key=lambda e: e.path)
    if errors:
        err = errors[0]
        loc = "/".join(str(p) for p in err.path) or "<root>"
        return False, f"{loc}: {err.message}"
    return True, None
