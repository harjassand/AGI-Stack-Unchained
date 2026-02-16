"""Candidate validation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from cdel.kernel.cost import count_term_nodes
from cdel.kernel.parse import parse_definition


@dataclass(frozen=True)
class Limits:
    max_new_symbols: int
    max_ast_nodes: int
    max_ast_depth: int


@dataclass(frozen=True)
class ValidatedCandidate:
    name: str
    payload: dict
    new_symbols: list[str]
    ast_nodes: int
    ast_depth: int


def validate_candidate(
    candidate: dict,
    *,
    limits: Limits,
    allowlist: set[str] | None = None,
) -> ValidatedCandidate:
    if not isinstance(candidate, dict):
        raise ValueError("candidate must be a dict")

    new_symbols = _require_list(candidate, "new_symbols")
    definitions = _require_list(candidate, "definitions")
    concepts = _require_list(candidate, "concepts")

    if not new_symbols:
        raise ValueError("candidate must define at least one new symbol")
    if len(new_symbols) > limits.max_new_symbols:
        raise ValueError("candidate exceeds max_new_symbols")
    if len(definitions) == 0 or len(definitions) > limits.max_new_symbols:
        raise ValueError("candidate definitions out of bounds")

    if not all(isinstance(item, str) and item for item in new_symbols):
        raise ValueError("new_symbols must be non-empty strings")

    ast_nodes = 0
    ast_depth = 0
    for definition in definitions:
        if not isinstance(definition, dict):
            raise ValueError("definition must be an object")
        try:
            parsed = parse_definition(definition)
        except Exception as exc:  # pragma: no cover - parser error detail varies
            raise ValueError(f"definition parse failed: {exc}") from exc
        ast_nodes += count_term_nodes(parsed.body)
        ast_depth = max(ast_depth, _count_depth(definition.get("body")))

    if ast_nodes > limits.max_ast_nodes:
        raise ValueError("candidate exceeds max_ast_nodes")
    if ast_depth > limits.max_ast_depth:
        raise ValueError("candidate exceeds max_ast_depth")

    if allowlist is not None:
        allow = set(allowlist) | set(new_symbols)
        referenced = _collect_symbol_refs(candidate)
        forbidden = sorted(name for name in referenced if name not in allow)
        if forbidden:
            raise ValueError(f"candidate references forbidden symbols: {', '.join(forbidden)}")

    payload = {
        "new_symbols": new_symbols,
        "definitions": definitions,
        "declared_deps": candidate.get("declared_deps") or [],
        "specs": candidate.get("specs") or [],
        "concepts": concepts,
    }
    name = new_symbols[0]
    return ValidatedCandidate(
        name=name,
        payload=payload,
        new_symbols=new_symbols,
        ast_nodes=ast_nodes,
        ast_depth=ast_depth,
    )


def _require_list(payload: dict, key: str) -> list:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"candidate missing required list: {key}")
    return value


def _count_depth(node: object) -> int:
    if not isinstance(node, dict):
        return 0
    depth = 1
    for value in node.values():
        if isinstance(value, dict):
            depth = max(depth, 1 + _count_depth(value))
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    depth = max(depth, 1 + _count_depth(item))
    return depth


def _collect_symbol_refs(candidate: dict) -> Iterable[str]:
    defs = candidate.get("definitions")
    if isinstance(defs, list):
        for definition in defs:
            if isinstance(definition, dict):
                body = definition.get("body")
                if isinstance(body, dict):
                    yield from _iter_sym_names(body)

    declared = candidate.get("declared_deps")
    if isinstance(declared, list):
        for name in declared:
            if isinstance(name, str):
                yield name


def _iter_sym_names(node: dict) -> Iterable[str]:
    stack = [node]
    while stack:
        current = stack.pop()
        if not isinstance(current, dict):
            continue
        if current.get("tag") == "sym":
            name = current.get("name")
            if isinstance(name, str):
                yield name
        for value in current.values():
            if isinstance(value, dict):
                stack.append(value)
            elif isinstance(value, list):
                for entry in value:
                    if isinstance(entry, dict):
                        stack.append(entry)
