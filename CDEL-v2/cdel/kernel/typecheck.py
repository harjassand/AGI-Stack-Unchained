"""Type checker for CDEL DSL."""

from __future__ import annotations

from dataclasses import dataclass

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
    Pair,
    Prim,
    Snd,
    Sym,
    Term,
    Var,
)
from cdel.kernel.types import BOOL, INT, FunType, ListType, OptionType, PairType, Type, type_norm


class TypeError(Exception):
    pass


def typecheck_definition(defn: Definition, sym_types: dict[str, Type]) -> Type:
    env: list[Type] = []
    for param in defn.params:
        env.insert(0, param.typ)
    return typecheck_term(defn.body, env, sym_types, expected=defn.ret_type)


def typecheck_term(term: Term, env: list[Type], sym_types: dict[str, Type], expected: Type | None = None) -> Type:
    if isinstance(term, Var):
        try:
            return env[term.idx]
        except IndexError as exc:
            raise TypeError("var index out of range") from exc
    if isinstance(term, Sym):
        if term.name not in sym_types:
            raise TypeError(f"unknown symbol: {term.name}")
        return sym_types[term.name]
    if isinstance(term, IntLit):
        return INT
    if isinstance(term, BoolLit):
        return BOOL
    if isinstance(term, Nil):
        if expected is None:
            raise TypeError("cannot infer type for nil")
        if not isinstance(expected, ListType):
            raise TypeError("nil must be a list")
        return expected
    if isinstance(term, OptionNone):
        if expected is None:
            raise TypeError("cannot infer type for none")
        if not isinstance(expected, OptionType):
            raise TypeError("none must be an option")
        return expected
    if isinstance(term, OptionSome):
        if isinstance(expected, OptionType):
            inner_type = typecheck_term(term.value, env, sym_types, expected=expected.elem)
            _ensure_type(inner_type, expected.elem, "some value")
            return expected
        inner_type = typecheck_term(term.value, env, sym_types)
        return OptionType(inner_type)
    if isinstance(term, Cons):
        if isinstance(expected, ListType):
            head_type = typecheck_term(term.head, env, sym_types, expected=expected.elem)
            tail_type = typecheck_term(term.tail, env, sym_types, expected=expected)
            _ensure_type(head_type, expected.elem, "cons head")
            _ensure_type(tail_type, expected, "cons tail")
            return expected
        head_type = typecheck_term(term.head, env, sym_types)
        tail_type = typecheck_term(term.tail, env, sym_types, expected=ListType(head_type))
        _ensure_type(tail_type, ListType(head_type), "cons tail")
        return ListType(head_type)
    if isinstance(term, If):
        cond_type = typecheck_term(term.cond, env, sym_types)
        _ensure_type(cond_type, BOOL, "if condition")
        if expected is not None:
            t_then = typecheck_term(term.then, env, sym_types, expected=expected)
            t_else = typecheck_term(term.els, env, sym_types, expected=expected)
            _ensure_type(t_then, expected, "if then")
            _ensure_type(t_else, expected, "if else")
            return expected
        t_then = typecheck_term(term.then, env, sym_types)
        t_else = typecheck_term(term.els, env, sym_types, expected=t_then)
        _ensure_type(t_else, t_then, "if else")
        return t_then
    if isinstance(term, Prim):
        return _typecheck_prim(term.op, term.args, env, sym_types, expected)
    if isinstance(term, Pair):
        if isinstance(expected, PairType):
            left_type = typecheck_term(term.left, env, sym_types, expected=expected.left)
            right_type = typecheck_term(term.right, env, sym_types, expected=expected.right)
            _ensure_type(left_type, expected.left, "pair left")
            _ensure_type(right_type, expected.right, "pair right")
            return expected
        left_type = typecheck_term(term.left, env, sym_types)
        right_type = typecheck_term(term.right, env, sym_types)
        return PairType(left_type, right_type)
    if isinstance(term, Fst):
        pair_type = typecheck_term(term.pair, env, sym_types)
        if not isinstance(pair_type, PairType):
            raise TypeError("fst expects a pair")
        if expected is not None:
            _ensure_type(pair_type.left, expected, "fst")
            return expected
        return pair_type.left
    if isinstance(term, Snd):
        pair_type = typecheck_term(term.pair, env, sym_types)
        if not isinstance(pair_type, PairType):
            raise TypeError("snd expects a pair")
        if expected is not None:
            _ensure_type(pair_type.right, expected, "snd")
            return expected
        return pair_type.right
    if isinstance(term, App):
        fn_type = typecheck_term(term.fn, env, sym_types)
        if not isinstance(fn_type, FunType):
            raise TypeError("attempt to apply non-function")
        if len(fn_type.args) != len(term.args):
            raise TypeError("arity mismatch")
        for arg, param_type in zip(term.args, fn_type.args):
            t_arg = typecheck_term(arg, env, sym_types, expected=param_type)
            _ensure_type(t_arg, param_type, "app arg")
        if expected is not None:
            _ensure_type(fn_type.ret, expected, "app return")
            return expected
        return fn_type.ret
    if isinstance(term, MatchList):
        scrutinee_type = typecheck_term(term.scrutinee, env, sym_types)
        if not isinstance(scrutinee_type, ListType):
            raise TypeError("match_list scrutinee must be list")
        head_type = scrutinee_type.elem
        tail_type = ListType(head_type)
        env2 = [tail_type, head_type] + env
        if expected is not None:
            t_nil = typecheck_term(term.nil_case, env, sym_types, expected=expected)
            t_cons = typecheck_term(term.cons_body, env2, sym_types, expected=expected)
            _ensure_type(t_nil, expected, "match nil_case")
            _ensure_type(t_cons, expected, "match cons_case")
            return expected
        t_nil = typecheck_term(term.nil_case, env, sym_types)
        t_cons = typecheck_term(term.cons_body, env2, sym_types, expected=t_nil)
        _ensure_type(t_cons, t_nil, "match cons_case")
        return t_nil
    if isinstance(term, MatchOption):
        scrutinee_type = typecheck_term(term.scrutinee, env, sym_types)
        if not isinstance(scrutinee_type, OptionType):
            raise TypeError("match_option scrutinee must be option")
        env2 = [scrutinee_type.elem] + env
        if expected is not None:
            t_none = typecheck_term(term.none_case, env, sym_types, expected=expected)
            t_some = typecheck_term(term.some_body, env2, sym_types, expected=expected)
            _ensure_type(t_none, expected, "match none_case")
            _ensure_type(t_some, expected, "match some_case")
            return expected
        t_none = typecheck_term(term.none_case, env, sym_types)
        t_some = typecheck_term(term.some_body, env2, sym_types, expected=t_none)
        _ensure_type(t_some, t_none, "match some_case")
        return t_none
    raise TypeError(f"unknown term: {term}")


def _typecheck_prim(op: str, args: tuple[Term, ...], env: list[Type], sym_types: dict[str, Type], expected: Type | None) -> Type:
    if op in {"add", "sub", "mul", "mod"}:
        _expect_prim_args(op, args, [INT, INT], env, sym_types)
        return INT
    if op in {"eq_int", "lt_int", "le_int"}:
        _expect_prim_args(op, args, [INT, INT], env, sym_types)
        return BOOL
    if op in {"and", "or"}:
        _expect_prim_args(op, args, [BOOL, BOOL], env, sym_types)
        return BOOL
    if op == "not":
        _expect_prim_args(op, args, [BOOL], env, sym_types)
        return BOOL
    raise TypeError(f"unknown prim op: {op}")


def _expect_prim_args(op: str, args: tuple[Term, ...], expected: list[Type], env: list[Type], sym_types: dict[str, Type]) -> None:
    if len(args) != len(expected):
        raise TypeError(f"prim {op} arity mismatch")
    for term, exp in zip(args, expected):
        t = typecheck_term(term, env, sym_types, expected=exp)
        _ensure_type(t, exp, f"prim {op}")


def _ensure_type(actual: Type, expected: Type, context: str) -> None:
    if actual != expected:
        raise TypeError(f"type mismatch in {context}: {type_norm(actual)} != {type_norm(expected)}")
