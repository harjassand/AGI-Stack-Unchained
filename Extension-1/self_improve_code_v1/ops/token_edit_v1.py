"""Token edit application (v1)."""

from __future__ import annotations

from typing import Tuple


class TokenEditError(ValueError):
    pass


def apply_edit_to_text(text: str, span: Tuple[int, int], replacement: str) -> str:
    start, end = span
    if start < 0 or end < start or end > len(text):
        raise TokenEditError("invalid span")
    return text[:start] + replacement + text[end:]


def read_text_normalized(path: str) -> str:
    with open(path, "rb") as f:
        data = f.read()
    text = data.decode("utf-8")
    return text.replace("\r\n", "\n")


def write_text_lf(path: str, text: str) -> None:
    with open(path, "wb") as f:
        f.write(text.replace("\r\n", "\n").encode("utf-8"))


__all__ = ["apply_edit_to_text", "read_text_normalized", "write_text_lf", "TokenEditError"]
