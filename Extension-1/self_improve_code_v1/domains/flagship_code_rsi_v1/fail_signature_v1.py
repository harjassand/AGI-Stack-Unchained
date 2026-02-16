"""Failure signature normalization (v1)."""

from __future__ import annotations

import re
from typing import Iterable

from ...canon.hash_v1 import sha256_hex


_ABS_PATH_RE = re.compile(r"(?:(?:[A-Za-z]:\\)|/)(?:[^\s:'\"]+[/\\])*[^\s:'\"]+")
_TIMESTAMP_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?)?\b"
)
_TIME_RE = re.compile(r"\b\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?\b")
_SPACE_RE = re.compile(r"\s+")

_STABLE_TOKENS: tuple[str, ...] = (
    "ERROR",
    "Error",
    "FAIL",
    "FAILED",
    "Failure",
    "Exception",
    "Traceback",
    "AssertionError",
    "KeyError",
    "TypeError",
    "ValueError",
    "IndexError",
    "AttributeError",
    "Timeout",
)


def _strip_paths(text: str) -> str:
    return _ABS_PATH_RE.sub("<PATH>", text)


def _strip_timestamps(text: str) -> str:
    text = _TIMESTAMP_RE.sub("<TS>", text)
    return _TIME_RE.sub("<TS>", text)


def _collapse_spaces(text: str) -> str:
    return _SPACE_RE.sub(" ", text).strip()


def _is_stable_line(line: str) -> bool:
    if not line:
        return False
    if line.startswith("E ") or line.startswith("F "):
        return True
    for token in _STABLE_TOKENS:
        if token in line:
            return True
    return False


def normalize_log(text: str) -> str:
    """Normalize logs to stable, comparable lines."""
    lines = text.splitlines()
    kept: list[str] = []
    for line in lines:
        line = _collapse_spaces(_strip_timestamps(_strip_paths(line)))
        if _is_stable_line(line):
            kept.append(line)
    return "\n".join(kept)


def failure_signature(normalized: str) -> str:
    return sha256_hex(normalized.encode("utf-8"))


def stable_lines(text: str) -> Iterable[str]:
    return normalize_log(text).splitlines()


__all__ = ["normalize_log", "failure_signature", "stable_lines"]
