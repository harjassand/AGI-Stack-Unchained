"""Context-guarded macro encoder for v2 macros."""

from __future__ import annotations

from typing import Any

from ..canon import canon_bytes


def _action_signature(action: dict[str, Any]) -> tuple[str, bytes]:
    name = action.get("name") if isinstance(action, dict) else None
    args = action.get("args") if isinstance(action, dict) else None
    if not isinstance(name, str):
        name = ""
    if not isinstance(args, dict):
        args = {}
    return name, canon_bytes(args)


def _body_signature(body: list[dict[str, Any]]) -> list[tuple[str, bytes]]:
    return [_action_signature(item) for item in body]


def _macro_guard_set(macro_def: dict[str, Any]) -> set[str]:
    guard = macro_def.get("guard") if isinstance(macro_def, dict) else None
    ctx_hashes = guard.get("ctx_hashes") if isinstance(guard, dict) else None
    if not isinstance(ctx_hashes, list):
        return set()
    return {str(x) for x in ctx_hashes if isinstance(x, str)}


def _macro_body(macro_def: dict[str, Any]) -> list[dict[str, Any]]:
    body = macro_def.get("body") if isinstance(macro_def, dict) else None
    if not isinstance(body, list):
        return []
    return [item for item in body if isinstance(item, dict)]


def macro_applies_at(events: list[dict[str, Any]], idx: int, macro_def: dict[str, Any]) -> bool:
    guard_set = _macro_guard_set(macro_def)
    if not guard_set:
        return False
    if idx >= len(events):
        return False
    ctx_hash = events[idx].get("onto_ctx_hash")
    if ctx_hash not in guard_set:
        return False
    body = _macro_body(macro_def)
    if not body:
        return False
    if idx + len(body) > len(events):
        return False
    body_sig = _body_signature(body)
    for offset, sig in enumerate(body_sig):
        action = events[idx + offset].get("action")
        if not isinstance(action, dict):
            return False
        if _action_signature(action) != sig:
            return False
    return True


def encode_tokens(
    events: list[dict[str, Any]],
    macros: list[dict[str, Any]],
) -> tuple[int, list[tuple[str, int, int]]]:
    """Return (token_count, occurrences) using greedy longest-match encoding."""
    compiled: list[tuple[str, int, list[tuple[str, bytes]], set[str]]] = []
    for macro in macros:
        body = _macro_body(macro)
        if not body:
            continue
        macro_id = macro.get("macro_id")
        if not isinstance(macro_id, str):
            continue
        compiled.append((macro_id, len(body), _body_signature(body), _macro_guard_set(macro)))

    tokens = 0
    occurrences: list[tuple[str, int, int]] = []
    i = 0
    while i < len(events):
        best = None
        for macro_id, length, body_sig, guard_set in compiled:
            if length <= 0 or i + length > len(events):
                continue
            ctx_hash = events[i].get("onto_ctx_hash")
            if ctx_hash not in guard_set:
                continue
            match = True
            for offset, sig in enumerate(body_sig):
                action = events[i + offset].get("action")
                if not isinstance(action, dict) or _action_signature(action) != sig:
                    match = False
                    break
            if not match:
                continue
            if best is None or length > best[1] or (length == best[1] and macro_id < best[0]):
                best = (macro_id, length)
        if best is None:
            tokens += 1
            i += 1
        else:
            tokens += 1
            macro_id, length = best
            occurrences.append((macro_id, i, length))
            i += length
    return tokens, occurrences
