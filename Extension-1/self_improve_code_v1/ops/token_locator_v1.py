"""Token span locator (v1)."""

from __future__ import annotations

import re
from typing import Dict, Tuple


class TokenLocationError(ValueError):
    pass


def _anchor_regions(content: str, before: str, after: str) -> list[Tuple[int, int]]:
    regions: list[Tuple[int, int]] = []
    pos = 0
    while True:
        idx = content.find(before, pos)
        if idx == -1:
            break
        start = idx + len(before)
        end = content.find(after, start)
        if end != -1:
            regions.append((start, end))
        pos = idx + 1
    return regions


def _select_region(content: str, selector: Dict) -> Tuple[int, int]:
    if "regex_single_match" in selector:
        pattern = selector["regex_single_match"]
        matches = list(re.finditer(pattern, content, flags=re.MULTILINE))
        if len(matches) != 1:
            raise TokenLocationError("regex_single_match did not match exactly once")
        return matches[0].span()

    before = selector.get("anchor_before")
    after = selector.get("anchor_after")
    if before is None or after is None:
        raise TokenLocationError("anchor selector missing anchor_before/anchor_after")
    regions = _anchor_regions(content, before, after)
    occ = selector.get("occurrence")
    if occ is None:
        if len(regions) != 1:
            raise TokenLocationError("anchor selector did not match exactly once")
        return regions[0]
    if occ < 0 or occ >= len(regions):
        raise TokenLocationError("anchor selector occurrence out of range")
    return regions[occ]


def locate_token_span(content: str, selector: Dict) -> Tuple[int, int]:
    start, end = _select_region(content, selector)
    if start > end:
        raise TokenLocationError("invalid region")
    region = content[start:end]
    stripped = region.strip()
    if not stripped:
        raise TokenLocationError("empty region after strip")
    lead = len(region) - len(region.lstrip())
    trail = len(region) - len(region.rstrip())
    token_start = start + lead
    token_end = end - trail
    if token_start >= token_end:
        raise TokenLocationError("invalid token span")
    return token_start, token_end


__all__ = ["locate_token_span", "TokenLocationError"]
