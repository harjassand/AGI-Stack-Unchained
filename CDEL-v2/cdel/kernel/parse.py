"""Parsing JSON AST into internal AST."""

from __future__ import annotations

from typing import Sequence

from cdel.kernel.ast import (
    App,
    BoolLit,
    Cons,
    Definition,
    Fst,
    If,
    IntLit,
    MatchList,
    MatchOption,
    Nil,
    OptionNone,
    OptionSome,
    Param,
    Pair,
    Prim,
    Snd,
    Sym,
    Term,
    Termination,
    Var,
)
from cdel.kernel.types import type_from_json


def parse_term(node: dict, env: list[str]) -> Term:
    if not isinstance(node, dict):
        raise ValueError("term must be an object")
    tag = node.get("tag")
    if tag == "var":
        name = node.get("name")
        if not isinstance(name, str):
            raise ValueError("var name must be a string")
        if name not in env:
            raise ValueError(f"unbound var: {name}")
        return Var(env.index(name))
    if tag == "sym":
        name = node.get("name")
        if not isinstance(name, str):
            raise ValueError("sym name must be a string")
        return Sym(name)
    if tag == "int":
        value = node.get("value")
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("int literal must be an int")
        return IntLit(value)
    if tag == "bool":
        value = node.get("value")
        if not isinstance(value, bool):
            raise ValueError("bool literal must be a bool")
        return BoolLit(value)
    if tag == "nil":
        return Nil()
    if tag == "none":
        return OptionNone()
    if tag == "some":
        return OptionSome(parse_term(node.get("value"), env))
    if tag == "cons":
        return Cons(
            parse_term(node.get("head"), env),
            parse_term(node.get("tail"), env),
        )
    if tag == "if":
        return If(
            parse_term(node.get("cond"), env),
            parse_term(node.get("then"), env),
            parse_term(node.get("else"), env),
        )
    if tag == "app":
        args = node.get("args")
        if not isinstance(args, list):
            raise ValueError("app args must be a list")
        return App(parse_term(node.get("fn"), env), tuple(parse_term(arg, env) for arg in args))
    if tag == "prim":
        args = node.get("args")
        if not isinstance(args, list):
            raise ValueError("prim args must be a list")
        return Prim(node.get("op"), tuple(parse_term(arg, env) for arg in args))
    if tag == "pair":
        return Pair(
            parse_term(node.get("left"), env),
            parse_term(node.get("right"), env),
        )
    if tag == "fst":
        return Fst(parse_term(node.get("pair"), env))
    if tag == "snd":
        return Snd(parse_term(node.get("pair"), env))
    if tag == "match_list":
        cons_case = node.get("cons_case")
        if not isinstance(cons_case, dict):
            raise ValueError("cons_case must be an object")
        head_var = cons_case.get("head_var")
        tail_var = cons_case.get("tail_var")
        if not isinstance(head_var, str) or not isinstance(tail_var, str):
            raise ValueError("cons_case head_var/tail_var must be strings")
        if head_var == tail_var:
            raise ValueError("cons_case head_var/tail_var must differ")
        env2 = [tail_var, head_var] + env
        return MatchList(
            parse_term(node.get("scrutinee"), env),
            parse_term(node.get("nil_case"), env),
            parse_term(cons_case.get("body"), env2),
        )
    if tag == "match_option":
        some_case = node.get("some_case")
        if not isinstance(some_case, dict):
            raise ValueError("some_case must be an object")
        some_var = some_case.get("var")
        if not isinstance(some_var, str):
            raise ValueError("some_case var must be a string")
        env2 = [some_var] + env
        return MatchOption(
            parse_term(node.get("scrutinee"), env),
            parse_term(node.get("none_case"), env),
            parse_term(some_case.get("body"), env2),
        )
    raise ValueError(f"unknown term tag: {tag}")


def parse_definition(defn: dict) -> Definition:
    name = defn.get("name")
    if not isinstance(name, str):
        raise ValueError("definition name must be a string")
    params_raw = defn.get("params") or []
    if not isinstance(params_raw, list):
        raise ValueError("params must be a list")
    params: list[Param] = []
    env: list[str] = []
    seen = set()
    for param in params_raw:
        pname = param.get("name")
        if not isinstance(pname, str):
            raise ValueError("param name must be a string")
        if pname in seen:
            raise ValueError("duplicate param name")
        seen.add(pname)
        ptype = type_from_json(param.get("type"))
        params.append(Param(name=pname, typ=ptype))
        env.insert(0, pname)
    ret_type = type_from_json(defn.get("ret_type"))
    body = parse_term(defn.get("body"), env)
    term_raw = defn.get("termination") or {}
    termination = Termination(
        kind=term_raw.get("kind"),
        decreases_param=term_raw.get("decreases_param"),
    )
    return Definition(
        name=name,
        params=tuple(params),
        ret_type=ret_type,
        body=body,
        termination=termination,
    )


def parse_specs_vars(vars_list: Sequence[dict]) -> tuple[list[str], list]:
    env: list[str] = []
    types = []
    seen = set()
    for var in vars_list:
        name = var.get("name")
        if not isinstance(name, str):
            raise ValueError("spec var name must be a string")
        if name in seen:
            raise ValueError("duplicate spec var name")
        seen.add(name)
        env.insert(0, name)
        types.append(type_from_json(var.get("type")))
    return env, types
