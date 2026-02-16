#!/usr/bin/env python3
import json
import sys
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except Exception as exc:
    print(f"jsonschema not available: {exc}")
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schema" / "receipt.schema.json"
RECEIPTS_DIR = ROOT / "receipt_examples"


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def main() -> int:
    schema = load_json(SCHEMA_PATH)
    validator = Draft202012Validator(schema)
    receipts = sorted(RECEIPTS_DIR.glob("*.json"))
    if not receipts:
        print("no receipt examples found")
        return 1

    for path in receipts:
        instance = load_json(path)
        errors = sorted(validator.iter_errors(instance), key=lambda e: e.path)
        if errors:
            err = errors[0]
            loc = "/".join(str(p) for p in err.path)
            print(f"receipt schema validation failed: {path}")
            print(f"location: {loc or '<root>'}")
            print(f"error: {err.message}")
            return 1

    print(f"receipt schema validation OK ({len(receipts)} examples)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
