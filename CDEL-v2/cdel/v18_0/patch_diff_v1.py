"""Deterministic unified diff helpers for CCAP patch emission."""

from __future__ import annotations

import difflib


def build_unified_patch_bytes(*, relpath: str, before_text: str, after_text: str) -> bytes:
    target_relpath = str(relpath).strip().replace("\\", "/")
    if not target_relpath:
        raise ValueError("relpath must be non-empty")
    if before_text == after_text:
        return b""
    rows = list(
        difflib.unified_diff(
            before_text.splitlines(),
            after_text.splitlines(),
            fromfile=f"a/{target_relpath}",
            tofile=f"b/{target_relpath}",
            lineterm="",
        )
    )
    if not rows:
        return b""
    return ("\n".join(rows) + "\n").encode("utf-8")


__all__ = ["build_unified_patch_bytes"]
