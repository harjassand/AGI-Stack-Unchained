"""Greedy longest-match encoder for macro tokenization."""

from __future__ import annotations

from typing import Any

from ..canon import canon_bytes


def action_key(action: dict[str, Any]) -> tuple[str, str]:
    name = action.get("name", "")
    args = action.get("args", {})
    return name, canon_bytes(args).decode("utf-8")


def macro_body_keys(macro_def: dict[str, Any]) -> list[tuple[str, str]]:
    return [action_key(op) for op in macro_def.get("body", [])]


def greedy_encode(
    actions: list[dict[str, Any]],
    macros: list[dict[str, Any]],
) -> tuple[int, dict[str, int]]:
    """Return (token_count, macro_token_counts) for the greedy longest-match encoder."""
    bodies: list[tuple[str, list[tuple[str, str]]]] = []
    for macro in macros:
        macro_id = macro.get("macro_id", "")
        if not macro_id:
            continue
        bodies.append((macro_id, macro_body_keys(macro)))
    idx = 0
    tokens = 0
    counts: dict[str, int] = {macro_id: 0 for macro_id, _ in bodies}
    action_keys = [action_key(action) for action in actions]
    while idx < len(action_keys):
        matches: list[tuple[int, str]] = []
        for macro_id, body in bodies:
            if idx + len(body) > len(action_keys):
                continue
            if action_keys[idx : idx + len(body)] == body:
                matches.append((len(body), macro_id))
        if matches:
            matches.sort(key=lambda item: (-item[0], item[1]))
            length, macro_id = matches[0]
            tokens += 1
            counts[macro_id] = counts.get(macro_id, 0) + 1
            idx += length
        else:
            tokens += 1
            idx += 1
    return tokens, counts
