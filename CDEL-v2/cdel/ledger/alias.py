"""Alias detection helpers."""

from __future__ import annotations

from cdel.kernel.ast import App, Sym, Var
from cdel.kernel.ast import Definition


def alias_target(defn: Definition) -> str | None:
    body = defn.body
    if not isinstance(body, App) or not isinstance(body.fn, Sym):
        return None
    if len(body.args) != len(defn.params):
        return None
    expected = len(defn.params) - 1
    for arg in body.args:
        if not isinstance(arg, Var) or arg.idx != expected:
            return None
        expected -= 1
    return body.fn.name
