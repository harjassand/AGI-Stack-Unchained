"""Patch stats (v1)."""

from __future__ import annotations

from typing import Dict


def patch_stats(patch_text: str) -> Dict[str, int]:
    lines = patch_text.splitlines()
    files_changed = 0
    lines_added = 0
    lines_removed = 0
    for line in lines:
        if line.startswith("--- a/"):
            files_changed += 1
            continue
        if line.startswith("+++") or line.startswith("@@"):
            continue
        if line.startswith("+"):
            lines_added += 1
        elif line.startswith("-"):
            lines_removed += 1
    return {
        "files_changed": files_changed,
        "lines_added": lines_added,
        "lines_removed": lines_removed,
        "patch_bytes": len(patch_text.encode("utf-8")),
    }


__all__ = ["patch_stats"]
