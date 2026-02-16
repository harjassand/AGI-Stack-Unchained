"""Helpers for Python unit-test domain payloads."""

from __future__ import annotations

from typing import Iterable


def python_source_payload(*, name: str, source: str, concept: str) -> dict:
    if not isinstance(source, str):
        raise ValueError("source must be a string")
    data = _encode_ascii(source)
    return {
        "new_symbols": [name],
        "definitions": [
            {
                "name": name,
                "params": [],
                "ret_type": {"tag": "list", "of": {"tag": "int"}},
                "body": _list_literal(data),
                "termination": {"kind": "structural", "decreases_param": None},
            }
        ],
        "declared_deps": [],
        "specs": [],
        "concepts": [{"concept": concept, "symbol": name}],
    }


def extract_python_source(payload: dict) -> str | None:
    if not isinstance(payload, dict):
        return None
    definitions = payload.get("definitions")
    if not isinstance(definitions, list) or not definitions:
        return None
    if len(definitions) != 1:
        return None
    definition = definitions[0]
    if not isinstance(definition, dict):
        return None
    body = definition.get("body")
    if not isinstance(body, dict):
        return None
    values = _decode_list(body)
    if values is None:
        return None
    try:
        return bytes(values).decode("ascii")
    except UnicodeDecodeError:
        return None


def _encode_ascii(text: str) -> list[int]:
    data = text.encode("ascii", errors="strict")
    return list(data)


def _list_literal(values: Iterable[int]) -> dict:
    term: dict = {"tag": "nil"}
    for value in reversed(list(values)):
        term = {
            "tag": "cons",
            "head": {"tag": "int", "value": value},
            "tail": term,
        }
    return term


def _decode_list(term: dict) -> list[int] | None:
    tag = term.get("tag")
    if tag == "nil":
        return []
    if tag != "cons":
        return None
    head = term.get("head")
    tail = term.get("tail")
    if not isinstance(head, dict) or not isinstance(tail, dict):
        return None
    if head.get("tag") != "int":
        return None
    value = head.get("value")
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    rest = _decode_list(tail)
    if rest is None:
        return None
    return [value] + rest
