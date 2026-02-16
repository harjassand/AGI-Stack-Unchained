"""Deterministic curriculum generator for CDEL tasks."""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path


def var(name: str) -> dict:
    return {"tag": "var", "name": name}


def sym(name: str) -> dict:
    return {"tag": "sym", "name": name}


def int_lit(value: int) -> dict:
    return {"tag": "int", "value": value}


def bool_lit(value: bool) -> dict:
    return {"tag": "bool", "value": value}


def none() -> dict:
    return {"tag": "none"}


def some(value: dict) -> dict:
    return {"tag": "some", "value": value}


def prim(op: str, *args: dict) -> dict:
    return {"tag": "prim", "op": op, "args": list(args)}


def app(fn: dict, *args: dict) -> dict:
    return {"tag": "app", "fn": fn, "args": list(args)}


def match_list(scrutinee: dict, nil_case: dict, head_var: str, tail_var: str, body: dict) -> dict:
    return {
        "tag": "match_list",
        "scrutinee": scrutinee,
        "nil_case": nil_case,
        "cons_case": {"head_var": head_var, "tail_var": tail_var, "body": body},
    }


def match_option(scrutinee: dict, none_case: dict, some_var: str, body: dict) -> dict:
    return {
        "tag": "match_option",
        "scrutinee": scrutinee,
        "none_case": none_case,
        "some_case": {"var": some_var, "body": body},
    }


def pair(left: dict, right: dict) -> dict:
    return {"tag": "pair", "left": left, "right": right}


def fst(term: dict) -> dict:
    return {"tag": "fst", "pair": term}


def snd(term: dict) -> dict:
    return {"tag": "snd", "pair": term}


def bool_eq(a: dict, b: dict) -> dict:
    return prim(
        "or",
        prim("and", a, b),
        prim("and", prim("not", a), prim("not", b)),
    )


def option_is_none(opt_term: dict) -> dict:
    return match_option(opt_term, bool_lit(True), "v", bool_lit(False))


def option_is_some(opt_term: dict) -> dict:
    return match_option(opt_term, bool_lit(False), "v", bool_lit(True))


def option_eq_int(opt_term: dict, expected: dict) -> dict:
    return match_option(opt_term, bool_lit(False), "ov", prim("eq_int", var("ov"), expected))


def list_is_nil(list_term: dict) -> dict:
    return match_list(list_term, bool_lit(True), "h", "t", bool_lit(False))


def list_head_eq(list_term: dict, expected: dict) -> dict:
    return match_list(list_term, bool_lit(False), "h", "t", prim("eq_int", var("h"), expected))


def forall(vars_list: list[dict], assert_term: dict, int_min: int = -2, int_max: int = 2, list_max_len: int = 3) -> dict:
    return {
        "kind": "forall",
        "vars": vars_list,
        "domain": {
            "int_min": int_min,
            "int_max": int_max,
            "list_max_len": list_max_len,
            "fun_symbols": [],
        },
        "assert": assert_term,
    }


def proof_eq(lhs: dict, rhs: dict) -> dict:
    return {
        "kind": "proof",
        "goal": {"tag": "eq", "lhs": lhs, "rhs": rhs},
        "proof": {"tag": "by_eval"},
    }


def proof_unbounded_eq(lhs: dict, rhs: dict) -> dict:
    return {
        "kind": "proof_unbounded",
        "goal": {"tag": "eq", "lhs": lhs, "rhs": rhs},
        "proof": {"tag": "missing"},
    }


def t_int() -> dict:
    return {"tag": "int"}


def t_list_int() -> dict:
    return {"tag": "list", "of": {"tag": "int"}}


def t_option_int() -> dict:
    return {"tag": "option", "of": {"tag": "int"}}


def t_pair_int_int() -> dict:
    return {"tag": "pair", "left": {"tag": "int"}, "right": {"tag": "int"}}


def t_pair_int_bool() -> dict:
    return {"tag": "pair", "left": {"tag": "int"}, "right": {"tag": "bool"}}


@dataclass(frozen=True)
class Template:
    base: str
    type_str: str
    allowed_deps: list[str]
    builder: callable


def task_is_zero(name: str) -> dict:
    n = var("n")
    return {
        "new_symbol": name,
        "type": "Int -> Bool",
        "allowed_deps": [],
        "specs": [forall([{"name": "n", "type": t_int()}], bool_eq(app(sym(name), n), prim("eq_int", n, int_lit(0))))],
        "proof_specs": [proof_eq(app(sym(name), int_lit(0)), bool_lit(True))],
    }


def task_inc(name: str) -> dict:
    n = var("n")
    return {
        "new_symbol": name,
        "type": "Int -> Int",
        "allowed_deps": [],
        "specs": [forall([{"name": "n", "type": t_int()}], prim("eq_int", app(sym(name), n), prim("add", n, int_lit(1))))],
        "proof_specs": [proof_eq(app(sym(name), int_lit(0)), int_lit(1))],
    }


def task_dec(name: str) -> dict:
    n = var("n")
    return {
        "new_symbol": name,
        "type": "Int -> Int",
        "allowed_deps": [],
        "specs": [forall([{"name": "n", "type": t_int()}], prim("eq_int", app(sym(name), n), prim("sub", n, int_lit(1))))],
        "proof_specs": [proof_eq(app(sym(name), int_lit(0)), int_lit(-1))],
    }


def task_add2(name: str) -> dict:
    n = var("n")
    return {
        "new_symbol": name,
        "type": "Int -> Int",
        "allowed_deps": [],
        "specs": [forall([{"name": "n", "type": t_int()}], prim("eq_int", app(sym(name), n), prim("add", n, int_lit(2))))],
        "proof_specs": [proof_eq(app(sym(name), int_lit(0)), int_lit(2))],
    }


def task_is_even(name: str) -> dict:
    n = var("n")
    return {
        "new_symbol": name,
        "type": "Int -> Bool",
        "allowed_deps": [],
        "specs": [
            forall(
                [{"name": "n", "type": t_int()}],
                bool_eq(app(sym(name), n), prim("eq_int", prim("mod", n, int_lit(2)), int_lit(0))),
            )
        ],
        "proof_specs": [proof_eq(app(sym(name), int_lit(0)), bool_lit(True))],
    }


def task_is_odd(name: str) -> dict:
    n = var("n")
    return {
        "new_symbol": name,
        "type": "Int -> Bool",
        "allowed_deps": [],
        "specs": [
            forall(
                [{"name": "n", "type": t_int()}],
                bool_eq(app(sym(name), n), prim("eq_int", prim("mod", n, int_lit(2)), int_lit(1))),
            )
        ],
        "proof_specs": [proof_eq(app(sym(name), int_lit(1)), bool_lit(True))],
    }


def task_len(name: str) -> dict:
    xs = var("xs")
    match_term = match_list(xs, int_lit(0), "h", "t", prim("add", int_lit(1), app(sym(name), var("t"))))
    return {
        "new_symbol": name,
        "type": "List[Int] -> Int",
        "allowed_deps": [],
        "specs": [
            forall(
                [{"name": "xs", "type": t_list_int()}],
                prim("eq_int", app(sym(name), xs), match_term),
                list_max_len=3,
            )
        ],
        "proof_specs": [proof_eq(app(sym(name), {"tag": "nil"}), int_lit(0))],
    }


def task_sum(name: str) -> dict:
    xs = var("xs")
    match_term = match_list(xs, int_lit(0), "h", "t", prim("add", var("h"), app(sym(name), var("t"))))
    return {
        "new_symbol": name,
        "type": "List[Int] -> Int",
        "allowed_deps": [],
        "specs": [
            forall(
                [{"name": "xs", "type": t_list_int()}],
                prim("eq_int", app(sym(name), xs), match_term),
                list_max_len=3,
            )
        ],
        "proof_specs": [proof_eq(app(sym(name), {"tag": "nil"}), int_lit(0))],
    }


def task_product(name: str) -> dict:
    xs = var("xs")
    match_term = match_list(xs, int_lit(1), "h", "t", prim("mul", var("h"), app(sym(name), var("t"))))
    return {
        "new_symbol": name,
        "type": "List[Int] -> Int",
        "allowed_deps": [],
        "specs": [
            forall(
                [{"name": "xs", "type": t_list_int()}],
                prim("eq_int", app(sym(name), xs), match_term),
                list_max_len=3,
            )
        ],
        "proof_specs": [proof_eq(app(sym(name), {"tag": "nil"}), int_lit(1))],
    }


def task_is_empty(name: str) -> dict:
    xs = var("xs")
    match_term = match_list(xs, bool_lit(True), "h", "t", bool_lit(False))
    return {
        "new_symbol": name,
        "type": "List[Int] -> Bool",
        "allowed_deps": [],
        "specs": [
            forall(
                [{"name": "xs", "type": t_list_int()}],
                bool_eq(app(sym(name), xs), match_term),
                list_max_len=3,
            )
        ],
        "proof_specs": [proof_eq(app(sym(name), {"tag": "nil"}), bool_lit(True))],
    }


def task_inc2(name: str) -> dict:
    n = var("n")
    return {
        "new_symbol": name,
        "type": "Int -> Int",
        "allowed_deps": ["inc"],
        "specs": [
            forall(
                [{"name": "n", "type": t_int()}],
                prim("eq_int", app(sym(name), n), app(sym("inc"), app(sym("inc"), n))),
            )
        ],
        "proof_specs": [proof_eq(app(sym(name), int_lit(0)), int_lit(2))],
    }


def task_add4(name: str) -> dict:
    n = var("n")
    return {
        "new_symbol": name,
        "type": "Int -> Int",
        "allowed_deps": ["add2"],
        "specs": [
            forall(
                [{"name": "n", "type": t_int()}],
                prim("eq_int", app(sym(name), n), app(sym("add2"), app(sym("add2"), n))),
            )
        ],
        "proof_specs": [proof_eq(app(sym(name), int_lit(0)), int_lit(4))],
    }


def task_len_id(name: str) -> dict:
    xs = var("xs")
    return {
        "new_symbol": name,
        "type": "List[Int] -> Int",
        "allowed_deps": ["len"],
        "specs": [
            forall(
                [{"name": "xs", "type": t_list_int()}],
                prim("eq_int", app(sym(name), xs), app(sym("len"), xs)),
                list_max_len=3,
            )
        ],
        "proof_specs": [proof_eq(app(sym(name), {"tag": "nil"}), int_lit(0))],
    }


def task_sum_id(name: str) -> dict:
    xs = var("xs")
    return {
        "new_symbol": name,
        "type": "List[Int] -> Int",
        "allowed_deps": ["sum"],
        "specs": [
            forall(
                [{"name": "xs", "type": t_list_int()}],
                prim("eq_int", app(sym(name), xs), app(sym("sum"), xs)),
                list_max_len=3,
            )
        ],
        "proof_specs": [proof_eq(app(sym(name), {"tag": "nil"}), int_lit(0))],
    }


def _module_task(
    name: str,
    params: list[dict],
    ret_type: dict,
    body: dict,
    specs: list[dict],
    declared_deps: list[str] | None = None,
    task_group: str | None = None,
) -> dict:
    module = {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": None,
        "payload": {
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
            "declared_deps": declared_deps or [],
            "specs": specs,
        },
    }
    task = {"module": module}
    if task_group:
        task["task_group"] = task_group
    return task


def make_option_module_tasks() -> list[dict]:
    tasks: list[dict] = []
    xs = var("xs")
    o = var("o")
    n = var("n")

    # head_opt: List[Int] -> Option[Int]
    head_body = match_list(xs, none(), "h", "t", some(var("h")))
    head_spec = match_list(
        xs,
        option_is_none(app(sym("head_opt"), xs)),
        "h",
        "t",
        option_eq_int(app(sym("head_opt"), xs), var("h")),
    )
    tasks.append(
        _module_task(
            "head_opt",
            [{"name": "xs", "type": t_list_int()}],
            t_option_int(),
            head_body,
            [forall([{"name": "xs", "type": t_list_int()}], head_spec, list_max_len=3)],
        )
    )

    # opt_default: Int -> Option[Int]
    tasks.append(
        _module_task(
            "opt_default",
            [{"name": "n", "type": t_int()}],
            t_option_int(),
            some(n),
            [forall([{"name": "n", "type": t_int()}], option_eq_int(app(sym("opt_default"), n), n))],
        )
    )

    # is_some_opt: Option[Int] -> Bool
    tasks.append(
        _module_task(
            "is_some_opt",
            [{"name": "o", "type": t_option_int()}],
            {"tag": "bool"},
            option_is_some(o),
            [forall([{"name": "o", "type": t_option_int()}], bool_eq(app(sym("is_some_opt"), o), option_is_some(o)))],
        )
    )

    # is_none_opt: Option[Int] -> Bool
    tasks.append(
        _module_task(
            "is_none_opt",
            [{"name": "o", "type": t_option_int()}],
            {"tag": "bool"},
            option_is_none(o),
            [forall([{"name": "o", "type": t_option_int()}], bool_eq(app(sym("is_none_opt"), o), option_is_none(o)))],
        )
    )

    # get_or_zero: Option[Int] -> Int
    get_body = match_option(o, int_lit(0), "v", var("v"))
    get_spec = match_option(
        o,
        prim("eq_int", app(sym("get_or_zero"), o), int_lit(0)),
        "v",
        prim("eq_int", app(sym("get_or_zero"), o), var("v")),
    )
    tasks.append(
        _module_task(
            "get_or_zero",
            [{"name": "o", "type": t_option_int()}],
            t_int(),
            get_body,
            [forall([{"name": "o", "type": t_option_int()}], get_spec)],
        )
    )

    # opt_inc: Option[Int] -> Option[Int]
    inc_body = match_option(o, none(), "v", some(prim("add", var("v"), int_lit(1))))
    inc_spec = match_option(
        o,
        option_is_none(app(sym("opt_inc"), o)),
        "v",
        option_eq_int(app(sym("opt_inc"), o), prim("add", var("v"), int_lit(1))),
    )
    tasks.append(
        _module_task(
            "opt_inc",
            [{"name": "o", "type": t_option_int()}],
            t_option_int(),
            inc_body,
            [forall([{"name": "o", "type": t_option_int()}], inc_spec)],
        )
    )

    # opt_add2: Option[Int] -> Option[Int]
    add2_body = match_option(o, none(), "v", some(prim("add", var("v"), int_lit(2))))
    add2_spec = match_option(
        o,
        option_is_none(app(sym("opt_add2"), o)),
        "v",
        option_eq_int(app(sym("opt_add2"), o), prim("add", var("v"), int_lit(2))),
    )
    tasks.append(
        _module_task(
            "opt_add2",
            [{"name": "o", "type": t_option_int()}],
            t_option_int(),
            add2_body,
            [forall([{"name": "o", "type": t_option_int()}], add2_spec)],
        )
    )

    # opt_add3: Option[Int] -> Option[Int]
    add3_body = match_option(o, none(), "v", some(prim("add", var("v"), int_lit(3))))
    add3_spec = match_option(
        o,
        option_is_none(app(sym("opt_add3"), o)),
        "v",
        option_eq_int(app(sym("opt_add3"), o), prim("add", var("v"), int_lit(3))),
    )
    tasks.append(
        _module_task(
            "opt_add3",
            [{"name": "o", "type": t_option_int()}],
            t_option_int(),
            add3_body,
            [forall([{"name": "o", "type": t_option_int()}], add3_spec)],
        )
    )

    # opt_add4: Option[Int] -> Option[Int]
    add4_body = match_option(o, none(), "v", some(prim("add", var("v"), int_lit(4))))
    add4_spec = match_option(
        o,
        option_is_none(app(sym("opt_add4"), o)),
        "v",
        option_eq_int(app(sym("opt_add4"), o), prim("add", var("v"), int_lit(4))),
    )
    tasks.append(
        _module_task(
            "opt_add4",
            [{"name": "o", "type": t_option_int()}],
            t_option_int(),
            add4_body,
            [forall([{"name": "o", "type": t_option_int()}], add4_spec)],
        )
    )

    # opt_add5: Option[Int] -> Option[Int]
    add5_body = match_option(o, none(), "v", some(prim("add", var("v"), int_lit(5))))
    add5_spec = match_option(
        o,
        option_is_none(app(sym("opt_add5"), o)),
        "v",
        option_eq_int(app(sym("opt_add5"), o), prim("add", var("v"), int_lit(5))),
    )
    tasks.append(
        _module_task(
            "opt_add5",
            [{"name": "o", "type": t_option_int()}],
            t_option_int(),
            add5_body,
            [forall([{"name": "o", "type": t_option_int()}], add5_spec)],
        )
    )

    # opt_is_zero: Option[Int] -> Bool
    is_zero_body = match_option(o, bool_lit(False), "v", prim("eq_int", var("v"), int_lit(0)))
    is_zero_spec = match_option(
        o,
        bool_eq(app(sym("opt_is_zero"), o), bool_lit(False)),
        "v",
        bool_eq(app(sym("opt_is_zero"), o), prim("eq_int", var("v"), int_lit(0))),
    )
    tasks.append(
        _module_task(
            "opt_is_zero",
            [{"name": "o", "type": t_option_int()}],
            {"tag": "bool"},
            is_zero_body,
            [forall([{"name": "o", "type": t_option_int()}], is_zero_spec)],
        )
    )

    # opt_is_one: Option[Int] -> Bool
    is_one_body = match_option(o, bool_lit(False), "v", prim("eq_int", var("v"), int_lit(1)))
    is_one_spec = match_option(
        o,
        bool_eq(app(sym("opt_is_one"), o), bool_lit(False)),
        "v",
        bool_eq(app(sym("opt_is_one"), o), prim("eq_int", var("v"), int_lit(1))),
    )
    tasks.append(
        _module_task(
            "opt_is_one",
            [{"name": "o", "type": t_option_int()}],
            {"tag": "bool"},
            is_one_body,
            [forall([{"name": "o", "type": t_option_int()}], is_one_spec)],
        )
    )

    # opt_is_two: Option[Int] -> Bool
    is_two_body = match_option(o, bool_lit(False), "v", prim("eq_int", var("v"), int_lit(2)))
    is_two_spec = match_option(
        o,
        bool_eq(app(sym("opt_is_two"), o), bool_lit(False)),
        "v",
        bool_eq(app(sym("opt_is_two"), o), prim("eq_int", var("v"), int_lit(2))),
    )
    tasks.append(
        _module_task(
            "opt_is_two",
            [{"name": "o", "type": t_option_int()}],
            {"tag": "bool"},
            is_two_body,
            [forall([{"name": "o", "type": t_option_int()}], is_two_spec)],
        )
    )

    # opt_is_three: Option[Int] -> Bool
    is_three_body = match_option(o, bool_lit(False), "v", prim("eq_int", var("v"), int_lit(3)))
    is_three_spec = match_option(
        o,
        bool_eq(app(sym("opt_is_three"), o), bool_lit(False)),
        "v",
        bool_eq(app(sym("opt_is_three"), o), prim("eq_int", var("v"), int_lit(3))),
    )
    tasks.append(
        _module_task(
            "opt_is_three",
            [{"name": "o", "type": t_option_int()}],
            {"tag": "bool"},
            is_three_body,
            [forall([{"name": "o", "type": t_option_int()}], is_three_spec)],
        )
    )

    # opt_is_even: Option[Int] -> Bool
    is_even_body = match_option(o, bool_lit(False), "v", prim("eq_int", prim("mod", var("v"), int_lit(2)), int_lit(0)))
    is_even_spec = match_option(
        o,
        bool_eq(app(sym("opt_is_even"), o), bool_lit(False)),
        "v",
        bool_eq(app(sym("opt_is_even"), o), prim("eq_int", prim("mod", var("v"), int_lit(2)), int_lit(0))),
    )
    tasks.append(
        _module_task(
            "opt_is_even",
            [{"name": "o", "type": t_option_int()}],
            {"tag": "bool"},
            is_even_body,
            [forall([{"name": "o", "type": t_option_int()}], is_even_spec)],
        )
    )

    # opt_mod2: Option[Int] -> Int
    mod2_body = match_option(o, int_lit(0), "v", prim("mod", var("v"), int_lit(2)))
    mod2_spec = match_option(
        o,
        prim("eq_int", app(sym("opt_mod2"), o), int_lit(0)),
        "v",
        prim("eq_int", app(sym("opt_mod2"), o), prim("mod", var("v"), int_lit(2))),
    )
    tasks.append(
        _module_task(
            "opt_mod2",
            [{"name": "o", "type": t_option_int()}],
            t_int(),
            mod2_body,
            [forall([{"name": "o", "type": t_option_int()}], mod2_spec)],
        )
    )

    # opt_mod3: Option[Int] -> Int
    mod3_body = match_option(o, int_lit(0), "v", prim("mod", var("v"), int_lit(3)))
    mod3_spec = match_option(
        o,
        prim("eq_int", app(sym("opt_mod3"), o), int_lit(0)),
        "v",
        prim("eq_int", app(sym("opt_mod3"), o), prim("mod", var("v"), int_lit(3))),
    )
    tasks.append(
        _module_task(
            "opt_mod3",
            [{"name": "o", "type": t_option_int()}],
            t_int(),
            mod3_body,
            [forall([{"name": "o", "type": t_option_int()}], mod3_spec)],
        )
    )

    # opt_neg: Option[Int] -> Option[Int]
    neg_body = match_option(o, none(), "v", some(prim("sub", int_lit(0), var("v"))))
    neg_spec = match_option(
        o,
        option_is_none(app(sym("opt_neg"), o)),
        "v",
        option_eq_int(app(sym("opt_neg"), o), prim("sub", int_lit(0), var("v"))),
    )
    tasks.append(
        _module_task(
            "opt_neg",
            [{"name": "o", "type": t_option_int()}],
            t_option_int(),
            neg_body,
            [forall([{"name": "o", "type": t_option_int()}], neg_spec)],
        )
    )

    # opt_nonneg: Option[Int] -> Bool
    nonneg_body = match_option(o, bool_lit(False), "v", prim("not", prim("lt_int", var("v"), int_lit(0))))
    nonneg_spec = match_option(
        o,
        bool_eq(app(sym("opt_nonneg"), o), bool_lit(False)),
        "v",
        bool_eq(app(sym("opt_nonneg"), o), prim("not", prim("lt_int", var("v"), int_lit(0)))),
    )
    tasks.append(
        _module_task(
            "opt_nonneg",
            [{"name": "o", "type": t_option_int()}],
            {"tag": "bool"},
            nonneg_body,
            [forall([{"name": "o", "type": t_option_int()}], nonneg_spec)],
        )
    )

    # opt_to_list: Option[Int] -> List[Int]
    to_list_body = match_option(o, {"tag": "nil"}, "v", {"tag": "cons", "head": var("v"), "tail": {"tag": "nil"}})
    to_list_spec = match_option(
        o,
        list_is_nil(app(sym("opt_to_list"), o)),
        "v",
        list_head_eq(app(sym("opt_to_list"), o), var("v")),
    )
    tasks.append(
        _module_task(
            "opt_to_list",
            [{"name": "o", "type": t_option_int()}],
            t_list_int(),
            to_list_body,
            [forall([{"name": "o", "type": t_option_int()}], to_list_spec)],
        )
    )

    return tasks


def make_pair_module_tasks() -> list[dict]:
    tasks: list[dict] = []
    xs = var("xs")
    p = var("p")

    # sum_len: List[Int] -> Pair[Int,Int]
    sum_len_body = pair(app(sym("sum"), xs), app(sym("len"), xs))
    sum_len_spec = prim(
        "and",
        prim("eq_int", fst(app(sym("sum_len"), xs)), app(sym("sum"), xs)),
        prim("eq_int", snd(app(sym("sum_len"), xs)), app(sym("len"), xs)),
    )
    tasks.append(
        _module_task(
            "sum_len",
            [{"name": "xs", "type": t_list_int()}],
            t_pair_int_int(),
            sum_len_body,
            [forall([{"name": "xs", "type": t_list_int()}], sum_len_spec, list_max_len=3)],
            declared_deps=["sum", "len"],
        )
    )

    # swap_pair: Pair[Int,Bool] -> Pair[Bool,Int]
    swap_body = pair(snd(p), fst(p))
    swap_spec = prim(
        "and",
        bool_eq(fst(app(sym("swap_pair"), p)), snd(p)),
        prim("eq_int", snd(app(sym("swap_pair"), p)), fst(p)),
    )
    tasks.append(
        _module_task(
            "swap_pair",
            [{"name": "p", "type": t_pair_int_bool()}],
            {"tag": "pair", "left": {"tag": "bool"}, "right": {"tag": "int"}},
            swap_body,
            [forall([{"name": "p", "type": t_pair_int_bool()}], swap_spec)],
        )
    )

    return tasks


def make_proof_unbounded_tasks() -> list[dict]:
    tasks: list[dict] = []
    group = "proof_only_core"

    tasks.append(
        _module_task(
            "zero_val",
            [],
            t_int(),
            int_lit(0),
            [proof_unbounded_eq(app(sym("zero_val")), int_lit(0))],
            task_group=group,
        )
    )
    tasks.append(
        _module_task(
            "one_val",
            [],
            t_int(),
            int_lit(1),
            [proof_unbounded_eq(app(sym("one_val")), int_lit(1))],
            task_group=group,
        )
    )
    tasks.append(
        _module_task(
            "two_val",
            [],
            t_int(),
            int_lit(2),
            [proof_unbounded_eq(app(sym("two_val")), int_lit(2))],
            task_group=group,
        )
    )
    tasks.append(
        _module_task(
            "len_nil_cert",
            [],
            t_int(),
            int_lit(0),
            [proof_unbounded_eq(app(sym("len"), {"tag": "nil"}), int_lit(0))],
            declared_deps=["len"],
            task_group=group,
        )
    )
    tasks.append(
        _module_task(
            "sum_nil_cert",
            [],
            t_int(),
            int_lit(0),
            [proof_unbounded_eq(app(sym("sum"), {"tag": "nil"}), int_lit(0))],
            declared_deps=["sum"],
            task_group=group,
        )
    )

    return tasks


def make_mutual_module_task(task_id: str) -> dict:
    module = {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": None,
        "payload": {
            "new_symbols": ["f", "g"],
            "definitions": [
                {
                    "name": "f",
                    "params": [{"name": "n", "type": t_int()}],
                    "ret_type": t_int(),
                    "body": app(sym("g"), var("n")),
                    "termination": {"kind": "structural", "decreases_param": None},
                },
                {
                    "name": "g",
                    "params": [{"name": "n", "type": t_int()}],
                    "ret_type": t_int(),
                    "body": app(sym("f"), var("n")),
                    "termination": {"kind": "structural", "decreases_param": None},
                },
            ],
            "declared_deps": [],
            "specs": [],
        },
    }
    return {"task_id": task_id, "module": module}


def make_bad_rec_module_task(task_id: str) -> dict:
    module = {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": None,
        "payload": {
            "new_symbols": ["len_bad"],
            "definitions": [
                {
                    "name": "len_bad",
                    "params": [{"name": "xs", "type": t_list_int()}],
                    "ret_type": t_int(),
                    "body": match_list(
                        var("xs"),
                        int_lit(0),
                        "h",
                        "t",
                        app(sym("len_bad"), var("xs")),
                    ),
                    "termination": {"kind": "structural", "decreases_param": "xs"},
                }
            ],
            "declared_deps": [],
            "specs": [],
        },
    }
    return {"task_id": task_id, "module": module}


BASE_TEMPLATES = [
    Template("is_zero", "Int -> Bool", [], task_is_zero),
    Template("inc", "Int -> Int", [], task_inc),
    Template("add2", "Int -> Int", [], task_add2),
    Template("len", "List[Int] -> Int", [], task_len),
    Template("sum", "List[Int] -> Int", [], task_sum),
]

EASY_TEMPLATES = [
    Template("dec", "Int -> Int", [], task_dec),
    Template("inc2", "Int -> Int", ["inc"], task_inc2),
    Template("add4", "Int -> Int", ["add2"], task_add4),
    Template("len_id", "List[Int] -> Int", ["len"], task_len_id),
    Template("sum_id", "List[Int] -> Int", ["sum"], task_sum_id),
]

HARD_TEMPLATES = [
    Template("is_even", "Int -> Bool", [], task_is_even),
    Template("is_odd", "Int -> Bool", [], task_is_odd),
    Template("product", "List[Int] -> Int", [], task_product),
    Template("is_empty", "List[Int] -> Bool", [], task_is_empty),
]


def _finalize_task(task: dict, certificate_mode: str, index: int, proof_every: int) -> dict:
    if "module" in task:
        task["certificate_mode"] = certificate_mode
        return task
    bounded_specs = task.pop("specs", [])
    proof_specs = task.pop("proof_specs", [])
    if certificate_mode == "bounded":
        task["specs"] = bounded_specs
        task["certificate_mode"] = "bounded"
        return task
    if certificate_mode == "proofheavy":
        task["specs"] = proof_specs
        task["certificate_mode"] = "proof"
        return task
    if certificate_mode == "mixed":
        if proof_every > 0 and (index + 1) % proof_every == 0:
            task["specs"] = bounded_specs + proof_specs
            task["certificate_mode"] = "proof"
        else:
            task["specs"] = bounded_specs
            task["certificate_mode"] = "bounded"
        return task
    raise ValueError(f"unknown certificate_mode: {certificate_mode}")


def generate_tasks(n: int, seed: int, certificate_mode: str = "bounded", proof_every: int = 10) -> list[dict]:
    rng = random.Random(seed)
    easy_templates = list(EASY_TEMPLATES)
    hard_templates = list(HARD_TEMPLATES)
    rng.shuffle(easy_templates)
    rng.shuffle(hard_templates)
    tasks: list[dict] = []
    used: set[str] = set()

    for template in BASE_TEMPLATES:
        task = template.builder(template.base)
        task = _finalize_task(task, certificate_mode, len(tasks), proof_every)
        task["task_id"] = f"T{len(tasks)+1:04d}"
        tasks.append(task)
        used.add(template.base)

    for module_task in make_option_module_tasks() + make_pair_module_tasks() + make_proof_unbounded_tasks():
        task = _finalize_task(module_task, certificate_mode, len(tasks), proof_every)
        task["task_id"] = f"T{len(tasks)+1:04d}"
        tasks.append(task)
        module_payload = task.get("module", {}).get("payload", {}) if isinstance(task.get("module"), dict) else {}
        for sym in module_payload.get("new_symbols") or []:
            used.add(sym)
        if len(tasks) >= n:
            return tasks[:n]

    idx = 0
    while len(tasks) < n:
        if len(tasks) in {200, 500, 800}:
            tasks.append(_finalize_task(make_mutual_module_task(f"R{len(tasks)+1:04d}"), certificate_mode, len(tasks), proof_every))
            tasks.append(_finalize_task(make_bad_rec_module_task(f"R{len(tasks)+2:04d}"), certificate_mode, len(tasks), proof_every))
            continue
        if len(tasks) in {300, 700}:
            # Redefinition attempt.
            task = task_inc("inc")
            task = _finalize_task(task, certificate_mode, len(tasks), proof_every)
            task["task_id"] = f"R{len(tasks)+1:04d}"
            tasks.append(task)
            continue
        template_pool = easy_templates if len(tasks) < 100 else (easy_templates + hard_templates)
        template = template_pool[idx % len(template_pool)]
        name = f"{template.base}_{idx}"
        while name in used:
            idx += 1
            name = f"{template.base}_{idx}"
        task = template.builder(name)
        task = _finalize_task(task, certificate_mode, len(tasks), proof_every)
        task["task_id"] = f"T{len(tasks)+1:04d}"
        tasks.append(task)
        used.add(name)
        idx += 1
    return tasks


def write_jsonl(tasks: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for task in tasks:
            fh.write(json.dumps(task, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", required=True)
    parser.add_argument("--mode", choices=["bounded", "proofheavy", "mixed"], default="bounded")
    parser.add_argument("--proof-every", type=int, default=10)
    args = parser.parse_args()

    tasks = generate_tasks(args.n, args.seed, certificate_mode=args.mode, proof_every=args.proof_every)
    write_jsonl(tasks, Path(args.out))


if __name__ == "__main__":
    main()
