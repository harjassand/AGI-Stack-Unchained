from __future__ import annotations

from typing import Any

from ...v1_7r.canon import canon_bytes, sha256_prefixed


def branch_signature_v1(rule_path: list[dict[str, Any]]) -> str:
    return sha256_prefixed(canon_bytes(rule_path))


__all__ = ["branch_signature_v1"]
