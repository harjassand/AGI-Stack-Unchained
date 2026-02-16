"""State IO helpers (v1)."""

from __future__ import annotations

import json
from typing import Any, Dict

from ..canon.json_canon_v1 import canon_bytes


def load_state(path: str) -> Dict[str, Any]:
    with open(path, "rb") as f:
        return json.loads(f.read().decode("utf-8"))


def save_state(path: str, state: Dict[str, Any]) -> None:
    with open(path, "wb") as f:
        f.write(canon_bytes(state))


__all__ = ["load_state", "save_state"]
