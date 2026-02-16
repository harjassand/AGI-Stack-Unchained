"""Attempt log helpers (v1)."""

from __future__ import annotations

from typing import Dict

from ..canon.jsonl_v1 import HISTORY_SEED_HEX, append_jsonl


def append_attempt(path: str, attempt: Dict, prev_digest_hex: str) -> str:
    return append_jsonl(path, attempt, prev_digest_hex)


def init_history_seed() -> str:
    return HISTORY_SEED_HEX


__all__ = ["append_attempt", "init_history_seed"]
