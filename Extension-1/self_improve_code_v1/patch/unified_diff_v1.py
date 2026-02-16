"""Unified diff generation (v1)."""

from __future__ import annotations

import difflib
from typing import Dict, Tuple


def unified_diff(changes: Dict[str, Tuple[str, str]]) -> str:
    diff_lines = []
    for path in sorted(changes.keys()):
        before, after = changes[path]
        if before == after:
            continue
        before_lines = before.splitlines(keepends=True)
        after_lines = after.splitlines(keepends=True)
        diff = difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            n=3,
            lineterm="\n",
        )
        diff_lines.extend(list(diff))
    return "".join(diff_lines)


__all__ = ["unified_diff"]
