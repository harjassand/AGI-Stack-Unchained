"""Canonical JSONL writer with rolling hash (v1)."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, Tuple

from .json_canon_v1 import canon_bytes
from .hash_v1 import sha256_bytes

HISTORY_SEED_HEX = "0" * 64


def _strip_history(record: Dict[str, Any]) -> Dict[str, Any]:
    if "history_digest" not in record:
        return record
    new_rec = dict(record)
    new_rec.pop("history_digest", None)
    return new_rec


def compute_history_digest(prev_hex: str, record: Dict[str, Any]) -> str:
    prev_bytes = bytes.fromhex(prev_hex)
    body = _strip_history(record)
    line_bytes = canon_bytes(body)
    digest = sha256_bytes(prev_bytes + line_bytes)
    return digest.hex()


def append_jsonl(path: str, record: Dict[str, Any], prev_hex: str) -> str:
    digest_hex = compute_history_digest(prev_hex, record)
    out_record = dict(record)
    out_record["history_digest"] = digest_hex
    line = canon_bytes(out_record) + b"\n"
    with open(path, "ab") as f:
        f.write(line)
    return digest_hex


def iter_jsonl(path: str) -> Iterable[Dict[str, Any]]:
    with open(path, "rb") as f:
        for raw in f:
            if not raw:
                continue
            obj = json.loads(raw.decode("utf-8"))
            yield obj


def verify_jsonl_rolling_hash(path: str, seed_hex: str = HISTORY_SEED_HEX) -> Tuple[bool, str]:
    prev = seed_hex
    for obj in iter_jsonl(path):
        expected = compute_history_digest(prev, obj)
        if obj.get("history_digest") != expected:
            return False, prev
        prev = expected
    return True, prev


__all__ = [
    "HISTORY_SEED_HEX",
    "append_jsonl",
    "iter_jsonl",
    "compute_history_digest",
    "verify_jsonl_rolling_hash",
]
