#!/usr/bin/env python3
"""GCJ-1 canonicalization for Genesis capsules."""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any

ZERO_HASH = "0" * 64
CANON_ID = "gcj-1"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp, parse_float=Decimal, parse_int=Decimal)


def decimal_to_canonical(value: Decimal) -> str:
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


def canonicalize(obj: Any) -> str:
    if obj is None:
        return "null"
    if obj is True:
        return "true"
    if obj is False:
        return "false"
    if isinstance(obj, Decimal):
        return decimal_to_canonical(obj)
    if isinstance(obj, (int, float)):
        return decimal_to_canonical(Decimal(str(obj)))
    if isinstance(obj, str):
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if isinstance(obj, list):
        return "[" + ",".join(canonicalize(x) for x in obj) + "]"
    if isinstance(obj, dict):
        for key in obj.keys():
            if not isinstance(key, str):
                raise ValueError("object keys must be strings")
        items = []
        for key in sorted(obj.keys()):
            items.append(canonicalize(key) + ":" + canonicalize(obj[key]))
        return "{" + ",".join(items) + "}"
    raise TypeError(f"unsupported type: {type(obj)}")


def canonical_bytes(obj: Any) -> bytes:
    return canonicalize(obj).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def capsule_hash(capsule_obj: dict) -> str:
    capsule = deepcopy(capsule_obj)
    commitments = capsule.get("commitments")
    if commitments is None:
        raise ValueError("capsule missing commitments")
    commitments["capsule_hash"] = ZERO_HASH
    return sha256_hex(canonical_bytes(capsule))


def receipt_hash(receipt_obj: dict) -> str:
    return sha256_hex(canonical_bytes(receipt_obj))


def receipt_log_hash(receipt_obj: dict) -> str:
    payload = {
        "capsule_hash": receipt_obj.get("capsule_hash", ""),
        "epoch_id": receipt_obj.get("epoch_id", ""),
        "budgets_spent": receipt_obj.get("budgets_spent", {}),
    }
    return sha256_hex(canonical_bytes(payload))
