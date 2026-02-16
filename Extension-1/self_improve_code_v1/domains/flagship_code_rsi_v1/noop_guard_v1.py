"""Semantic no-op detector (v1.1)."""

from __future__ import annotations


_DIFF_HEADER_PREFIXES = (
    "diff --git",
    "index ",
    "--- ",
    "+++ ",
    "@@",
)

_COMMENT_PREFIXES = ("#", "//", "/*", "*/", "*")


def _is_comment_only(line: str) -> bool:
    stripped = line.lstrip()
    if not stripped:
        return True
    for prefix in _COMMENT_PREFIXES:
        if stripped.startswith(prefix):
            return True
    return False


def is_semantic_noop(diff_text: str) -> bool:
    """Return True if diff only changes whitespace or comment-only lines."""
    added: list[str] = []
    removed: list[str] = []
    for raw in diff_text.splitlines():
        if raw.startswith(_DIFF_HEADER_PREFIXES):
            continue
        if not raw or raw[0] not in {"+", "-"}:
            continue
        if raw.startswith("+++ ") or raw.startswith("--- "):
            continue
        line = raw[1:]
        if line.strip() == "":
            continue
        if _is_comment_only(line):
            continue
        normalized = line.rstrip()
        if raw[0] == "+":
            added.append(normalized)
        else:
            removed.append(normalized)

    if not added and not removed:
        return True
    if sorted(added) == sorted(removed):
        return True
    return False


__all__ = ["is_semantic_noop"]
