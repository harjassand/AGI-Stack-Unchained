"""Deterministic proposal inbox loader for v1.7r demon campaigns."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed


def load_proposals_dir(root: Path) -> list[dict[str, Any]]:
    if not root.exists():
        raise CanonError(f"missing proposals dir: {root}")
    proposals: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(root.glob("*.json")):
        payload = load_canon_json(path)
        digest = sha256_prefixed(canon_bytes(payload))
        proposals.append((digest, payload))
    proposals.sort(key=lambda item: item[0])
    return [payload for _hash, payload in proposals]
