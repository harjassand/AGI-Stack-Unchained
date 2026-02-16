"""Compose edit sets deterministically (v1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from .token_edit_v1 import apply_edit_to_text


@dataclass(frozen=True)
class Edit:
    file_relpath: str
    start: int
    end: int
    replacement: str


def compose_edits(edits: List[Edit], max_spans_per_file: int) -> Dict[str, List[Edit]]:
    by_file: Dict[str, List[Edit]] = {}
    for edit in edits:
        by_file.setdefault(edit.file_relpath, []).append(edit)

    for file_relpath, file_edits in by_file.items():
        if len(file_edits) > max_spans_per_file:
            raise ValueError("too many spans per file")
        file_edits.sort(key=lambda e: (e.start, e.end, e.replacement))
        last_end = -1
        for e in file_edits:
            if e.start < last_end:
                raise ValueError("overlapping edit spans")
            last_end = e.end
    return by_file


def apply_edits(text: str, edits: List[Edit]) -> str:
    # Apply in reverse order to keep spans stable.
    for e in sorted(edits, key=lambda x: (x.start, x.end), reverse=True):
        text = apply_edit_to_text(text, (e.start, e.end), e.replacement)
    return text


__all__ = ["Edit", "compose_edits", "apply_edits"]
