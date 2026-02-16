#!/usr/bin/env python3
import json
import sys
from decimal import Decimal
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except Exception as exc:
    print(f"jsonschema not available: {exc}")
    sys.exit(2)

TOOLS_DIR = Path(__file__).resolve().parent
ROOT = TOOLS_DIR.parents[0]

sys.path.insert(0, str(TOOLS_DIR))
import canonicalize as canon  # noqa: E402

SCHEMA_PATH = ROOT / "schema" / "receipt.schema.json"


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def to_decimal(value) -> Decimal:
    return Decimal(str(value))


def validate_schema(receipt_obj) -> None:
    with SCHEMA_PATH.open("r", encoding="utf-8") as fp:
        schema = json.load(fp)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(receipt_obj), key=lambda e: e.path)
    if errors:
        err = errors[0]
        loc = "/".join(str(p) for p in err.path)
        raise ValueError(f"receipt schema error at {loc or '<root>'}: {err.message}")


def ensure_nonempty(value, name: str) -> None:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"{name} is required")


def verify(receipt_path: Path, capsule_path: Path) -> None:
    receipt = load_json(receipt_path)
    capsule = load_json(capsule_path)

    validate_schema(receipt)

    capsule_hash = canon.compute_capsule_hash(canon.load_json(capsule_path))
    if receipt["capsule_hash"] != capsule_hash:
        raise ValueError("capsule_hash mismatch")

    ensure_nonempty(receipt.get("epoch_id"), "epoch_id")
    ensure_nonempty(receipt.get("measurement_transcript_hash"), "measurement_transcript_hash")
    ensure_nonempty(receipt.get("rng_commitment_id"), "rng_commitment_id")

    budgets_spent = receipt["budgets_spent"]
    bid = capsule["budget_bid"]

    if to_decimal(budgets_spent["alpha_spent"]) > to_decimal(bid["alpha_bid"]):
        raise ValueError("alpha_spent exceeds bid")

    if to_decimal(budgets_spent["privacy_spent"]["epsilon_spent"]) > to_decimal(bid["privacy_bid"]["epsilon"]):
        raise ValueError("epsilon_spent exceeds bid")

    if to_decimal(budgets_spent["privacy_spent"]["delta_spent"]) > to_decimal(bid["privacy_bid"]["delta"]):
        raise ValueError("delta_spent exceeds bid")

    if to_decimal(budgets_spent["compute_spent"]["compute_units"]) > to_decimal(bid["compute_bid"]["max_compute_units"]):
        raise ValueError("compute_units exceeds bid")

    if to_decimal(budgets_spent["compute_spent"]["wall_time_ms"]) > to_decimal(bid["compute_bid"]["max_wall_time_ms"]):
        raise ValueError("wall_time_ms exceeds bid")

    if to_decimal(budgets_spent["compute_spent"]["adversary_strength_used"]) > to_decimal(bid["compute_bid"]["max_adversary_strength"]):
        raise ValueError("adversary_strength_used exceeds bid")



def main() -> int:
    if len(sys.argv) != 3:
        print("usage: verify_receipt.py <receipt.json> <capsule.json>")
        return 2

    receipt_path = Path(sys.argv[1])
    capsule_path = Path(sys.argv[2])

    try:
        verify(receipt_path, capsule_path)
    except Exception as exc:
        print(f"receipt verification failed: {exc}")
        return 1

    print("receipt verification OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
