"""Build deterministic policy payloads from plan steps."""

from __future__ import annotations

from typing import Any


def tooluse_policy_payload(*, name: str, concept: str, action_sequence: list[int]) -> dict[str, Any]:
    params = [
        {"name": "step", "type": {"tag": "int"}},
        {"name": "last_ok", "type": {"tag": "int"}},
        {"name": "last_len", "type": {"tag": "int"}},
    ]
    body = _action_chain(action_sequence)
    return {
        "new_symbols": [name],
        "definitions": [
            {
                "name": name,
                "params": params,
                "ret_type": {"tag": "int"},
                "body": body,
                "termination": {"kind": "structural", "decreases_param": None},
            }
        ],
        "declared_deps": [],
        "specs": [],
        "concepts": [{"concept": concept, "symbol": name}],
    }


def wrapper_policy_payload(*, name: str, concept: str, target_symbol: str, type_norm: str) -> dict[str, Any]:
    parsed = _parse_fun_signature(type_norm)
    if parsed is None:
        raise ValueError("unsupported type signature")
    params, ret_type = parsed
    body = {
        "tag": "app",
        "fn": {"tag": "sym", "name": target_symbol},
        "args": [{"tag": "var", "name": param["name"]} for param in params],
    }
    return {
        "new_symbols": [name],
        "definitions": [
            {
                "name": name,
                "params": params,
                "ret_type": ret_type,
                "body": body,
                "termination": {"kind": "structural", "decreases_param": None},
            }
        ],
        "declared_deps": [target_symbol],
        "specs": [],
        "concepts": [{"concept": concept, "symbol": name}],
    }


def _action_chain(actions: list[int]) -> dict[str, Any]:
    expr: dict[str, Any] = {"tag": "int", "value": -1}
    for idx in reversed(range(len(actions))):
        expr = {
            "tag": "if",
            "cond": _eq_step(idx),
            "then": {"tag": "int", "value": actions[idx]},
            "else": expr,
        }
    return expr


def _eq_step(value: int) -> dict[str, Any]:
    return {
        "tag": "prim",
        "op": "eq_int",
        "args": [
            {"tag": "var", "name": "step"},
            {"tag": "int", "value": value},
        ],
    }


def _parse_fun_signature(type_norm: str) -> tuple[list[dict], dict] | None:
    parts = _split_top_level_arrows(type_norm)
    if len(parts) < 2:
        return None
    arg_types = parts[:-1]
    ret_type = _parse_type(parts[-1])
    if ret_type is None:
        return None
    params = []
    for idx, arg in enumerate(arg_types):
        parsed = _parse_type(arg)
        if parsed is None:
            return None
        params.append({"name": f"a{idx}", "type": parsed})
    return params, ret_type


def _split_top_level_arrows(type_norm: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    i = 0
    while i < len(type_norm):
        ch = type_norm[i]
        if ch in "([":
            depth += 1
            buf.append(ch)
            i += 1
            continue
        if ch in ")]":
            depth = max(0, depth - 1)
            buf.append(ch)
            i += 1
            continue
        if depth == 0 and type_norm[i : i + 2] == "->":
            part = "".join(buf).strip()
            if part:
                parts.append(part)
            buf = []
            i += 2
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def _parse_type(type_norm: str) -> dict | None:
    text = type_norm.strip()
    if text == "Int":
        return {"tag": "int"}
    if text == "Bool":
        return {"tag": "bool"}
    if text.startswith("List[") and text.endswith("]"):
        inner = text[5:-1]
        elem = _parse_type(inner)
        return None if elem is None else {"tag": "list", "of": elem}
    if text.startswith("Option[") and text.endswith("]"):
        inner = text[7:-1]
        elem = _parse_type(inner)
        return None if elem is None else {"tag": "option", "of": elem}
    if text.startswith("Pair[") and text.endswith("]"):
        inner = text[5:-1]
        left_text, right_text = _split_pair(inner)
        left = _parse_type(left_text)
        right = _parse_type(right_text)
        if left is None or right is None:
            return None
        return {"tag": "pair", "left": left, "right": right}
    return None


def _split_pair(inner: str) -> tuple[str, str]:
    depth = 0
    for idx, ch in enumerate(inner):
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        elif ch == "," and depth == 0:
            return inner[:idx].strip(), inner[idx + 1 :].strip()
    return inner.strip(), ""
