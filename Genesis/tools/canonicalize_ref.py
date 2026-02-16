#!/usr/bin/env python3
import argparse
import json
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parents[1]
TEST_VECTORS = ROOT / "test_vectors"
ZERO_HASH = "0" * 64
CANON_ID = "gcj-1"


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp, parse_float=Decimal, parse_int=Decimal)


def dec_to_str(value: Decimal) -> str:
    if value.is_nan() or value.is_infinite():
        raise ValueError("non-finite numbers are not allowed")
    if value.is_zero():
        return "0"

    sign = "-" if value.is_signed() else ""
    value = abs(value)
    tup = value.as_tuple()
    digits = "".join(str(d) for d in tup.digits) or "0"
    exp = tup.exponent

    if exp >= 0:
        int_part = digits + ("0" * exp)
        frac_part = ""
    else:
        idx = len(digits) + exp
        if idx > 0:
            int_part = digits[:idx]
            frac_part = digits[idx:]
        else:
            int_part = "0"
            frac_part = ("0" * (-idx)) + digits

    int_part = int_part.lstrip("0") or "0"
    frac_part = frac_part.rstrip("0")

    if frac_part:
        return f"{sign}{int_part}.{frac_part}"
    return f"{sign}{int_part}"


def canonical(obj) -> str:
    if obj is None:
        return "null"
    if obj is True:
        return "true"
    if obj is False:
        return "false"
    if isinstance(obj, Decimal):
        return dec_to_str(obj)
    if isinstance(obj, str):
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if isinstance(obj, list):
        return "[" + ",".join(canonical(item) for item in obj) + "]"
    if isinstance(obj, dict):
        for key in obj.keys():
            if not isinstance(key, str):
                raise ValueError("object keys must be strings")
        parts = []
        for key in sorted(obj.keys()):
            parts.append(canonical(key) + ":" + canonical(obj[key]))
        return "{" + ",".join(parts) + "}"
    raise TypeError(f"unsupported type: {type(obj)}")


def canonical_bytes(obj) -> bytes:
    return canonical(obj).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_capsule_hash(capsule_obj) -> str:
    capsule = deepcopy(capsule_obj)
    commitments = capsule.get("commitments")
    if commitments is None:
        raise ValueError("capsule missing commitments")
    commitments["capsule_hash"] = ZERO_HASH
    return sha256_hex(canonical_bytes(capsule))


def compute_receipt_hash(receipt_obj) -> str:
    return sha256_hex(canonical_bytes(receipt_obj))


def compute_transcript_hash(transcript_obj) -> str:
    return sha256_hex(canonical_bytes(transcript_obj))


def verify_vectors() -> int:
    capsule = load_json(TEST_VECTORS / "capsule_minimal.json")
    receipt = load_json(TEST_VECTORS / "receipt_minimal.json")
    transcript = load_json(TEST_VECTORS / "transcript_minimal.json")

    capsule_expected = (TEST_VECTORS / "capsule_minimal.hash.txt").read_text(encoding="utf-8").strip()
    receipt_expected = (TEST_VECTORS / "receipt_minimal.hash.txt").read_text(encoding="utf-8").strip()
    transcript_expected = (TEST_VECTORS / "transcript_minimal.hash.txt").read_text(encoding="utf-8").strip()

    capsule_hash = compute_capsule_hash(capsule)
    receipt_hash = compute_receipt_hash(receipt)
    transcript_hash = compute_transcript_hash(transcript)

    if capsule_hash != capsule_expected:
        print(f"capsule hash mismatch: {capsule_hash} != {capsule_expected}")
        return 1
    if receipt_hash != receipt_expected:
        print(f"receipt hash mismatch: {receipt_hash} != {receipt_expected}")
        return 1
    if transcript_hash != transcript_expected:
        print(f"transcript hash mismatch: {transcript_hash} != {transcript_expected}")
        return 1

    print("canonicalization ref vectors OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="GCJ-1 canonicalization reference tool")
    parser.add_argument("--verify", action="store_true", help="verify test vectors")
    parser.add_argument("--id", action="store_true", help="print canonicalization id")
    args = parser.parse_args()

    if args.id:
        print(CANON_ID)
        return 0
    if args.verify:
        return verify_vectors()

    parser.print_usage()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
