"""Template-based proposer."""

from __future__ import annotations

import random

from orchestrator.types import Candidate, ContextBundle
from orchestrator.proposer.base import Proposer


class TemplateProposer(Proposer):
    def __init__(self, max_new_symbols: int = 1) -> None:
        self.max_new_symbols = max_new_symbols

    def propose(self, *, context: ContextBundle, budget: int, rng_seed: int) -> list[Candidate]:
        rng = random.Random(rng_seed)
        candidate_name = f"{context.concept}_tmpl_{rng.randint(1000, 9999)}"
        parsed = _parse_fun_signature(context.type_norm)
        if parsed is None:
            return []
        params, ret_type = parsed
        param_vars = [p["name"] for p in params]
        body = {
            "tag": "app",
            "fn": {"tag": "sym", "name": context.oracle_symbol},
            "args": [{"tag": "var", "name": name} for name in param_vars],
        }
        payload = {
            "new_symbols": [candidate_name],
            "definitions": [
                {
                    "name": candidate_name,
                    "params": params,
                    "ret_type": ret_type,
                    "body": body,
                    "termination": {"kind": "structural", "decreases_param": None},
                }
            ],
            "declared_deps": [context.oracle_symbol],
            "specs": [],
            "concepts": [{"concept": context.concept, "symbol": candidate_name}],
        }
        return [Candidate(name=candidate_name, payload=payload, proposer="template", notes="oracle-wrapper")]


def _parse_fun_signature(type_norm: str) -> tuple[list[dict], dict] | None:
    parts = _split_top_level_arrows(type_norm)
    if len(parts) < 2:
        return None
    arg_types = parts[:-1]
    ret_type = _parse_type(arg_types[-1]) if False else _parse_type(parts[-1])
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
