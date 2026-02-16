"""Deterministic evaluator with step limit."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

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
from cdel.kernel.types import BOOL, INT, FunType, ListType, Type


class EvalError(Exception):
    pass


@dataclass(frozen=True)
class IntVal:
    value: int


@dataclass(frozen=True)
class BoolVal:
    value: bool


@dataclass(frozen=True)
class ListVal:
    items: tuple[object, ...]


@dataclass(frozen=True)
class OptionVal:
    is_some: bool
    value: object | None


@dataclass(frozen=True)
class PairVal:
    left: object
    right: object


@dataclass(frozen=True)
class FunVal:
    name: str


Value = IntVal | BoolVal | ListVal | OptionVal | PairVal | FunVal


class Evaluator:
    def __init__(self, step_limit: int) -> None:
        self.step_limit = step_limit
        self.steps = 0

    def _tick(self) -> None:
        self.steps += 1
        if self.steps > self.step_limit:
            raise EvalError("evaluation exceeded step limit")

    def eval_term(self, term: Term, env: list[Value], defs: dict[str, Definition]) -> Value:
        self._tick()
        if isinstance(term, Var):
            try:
                return env[term.idx]
            except IndexError as exc:
                raise EvalError("var index out of range") from exc
        if isinstance(term, Sym):
            return FunVal(term.name)
        if isinstance(term, IntLit):
            return IntVal(term.value)
        if isinstance(term, BoolLit):
            return BoolVal(term.value)
        if isinstance(term, Nil):
            return ListVal(tuple())
        if isinstance(term, OptionNone):
            return OptionVal(False, None)
        if isinstance(term, OptionSome):
            value = self.eval_term(term.value, env, defs)
            return OptionVal(True, value)
        if isinstance(term, Cons):
            head = self.eval_term(term.head, env, defs)
            tail = self.eval_term(term.tail, env, defs)
            if not isinstance(tail, ListVal):
                raise EvalError("cons tail must be list")
            return ListVal((head,) + tail.items)
        if isinstance(term, Pair):
            left = self.eval_term(term.left, env, defs)
            right = self.eval_term(term.right, env, defs)
            return PairVal(left, right)
        if isinstance(term, Fst):
            pair_val = self.eval_term(term.pair, env, defs)
            if not isinstance(pair_val, PairVal):
                raise EvalError("fst expects a pair")
            return pair_val.left
        if isinstance(term, Snd):
            pair_val = self.eval_term(term.pair, env, defs)
            if not isinstance(pair_val, PairVal):
                raise EvalError("snd expects a pair")
            return pair_val.right
        if isinstance(term, If):
            cond = self.eval_term(term.cond, env, defs)
            if not isinstance(cond, BoolVal):
                raise EvalError("if condition must be bool")
            branch = term.then if cond.value else term.els
            return self.eval_term(branch, env, defs)
        if isinstance(term, Prim):
            args = [self.eval_term(arg, env, defs) for arg in term.args]
            return _eval_prim(term.op, args)
        if isinstance(term, App):
            fn_val = self.eval_term(term.fn, env, defs)
            args = [self.eval_term(arg, env, defs) for arg in term.args]
            return self._apply(fn_val, args, defs)
        if isinstance(term, MatchList):
            scrutinee = self.eval_term(term.scrutinee, env, defs)
            if not isinstance(scrutinee, ListVal):
                raise EvalError("match_list scrutinee must be list")
            if not scrutinee.items:
                return self.eval_term(term.nil_case, env, defs)
            head = scrutinee.items[0]
            tail = ListVal(scrutinee.items[1:])
            env2 = [tail, head] + env
            return self.eval_term(term.cons_body, env2, defs)
        if isinstance(term, MatchOption):
            scrutinee = self.eval_term(term.scrutinee, env, defs)
            if not isinstance(scrutinee, OptionVal):
                raise EvalError("match_option scrutinee must be option")
            if not scrutinee.is_some:
                return self.eval_term(term.none_case, env, defs)
            env2 = [scrutinee.value] + env
            return self.eval_term(term.some_body, env2, defs)
        raise EvalError(f"unknown term: {term}")

    def _apply(self, fn_val: Value, args: list[Value], defs: dict[str, Definition]) -> Value:
        if not isinstance(fn_val, FunVal):
            raise EvalError("attempted to apply non-function")
        if fn_val.name not in defs:
            raise EvalError(f"unknown symbol: {fn_val.name}")
        definition = defs[fn_val.name]
        if len(args) != len(definition.params):
            raise EvalError("arity mismatch")
        env: list[Value] = []
        for arg in args:
            env.insert(0, arg)
        return self.eval_term(definition.body, env, defs)


def _eval_prim(op: str, args: list[Value]) -> Value:
    if op == "add":
        _require_arity(op, args, 2)
        return IntVal(_int(args[0]) + _int(args[1]))
    if op == "sub":
        _require_arity(op, args, 2)
        return IntVal(_int(args[0]) - _int(args[1]))
    if op == "mul":
        _require_arity(op, args, 2)
        return IntVal(_int(args[0]) * _int(args[1]))
    if op == "mod":
        _require_arity(op, args, 2)
        return IntVal(_int(args[0]) % _int(args[1]))
    if op == "eq_int":
        _require_arity(op, args, 2)
        return BoolVal(_int(args[0]) == _int(args[1]))
    if op == "lt_int":
        _require_arity(op, args, 2)
        return BoolVal(_int(args[0]) < _int(args[1]))
    if op == "le_int":
        _require_arity(op, args, 2)
        return BoolVal(_int(args[0]) <= _int(args[1]))
    if op == "and":
        _require_arity(op, args, 2)
        return BoolVal(_bool(args[0]) and _bool(args[1]))
    if op == "or":
        _require_arity(op, args, 2)
        return BoolVal(_bool(args[0]) or _bool(args[1]))
    if op == "not":
        _require_arity(op, args, 1)
        return BoolVal(not _bool(args[0]))
    raise EvalError(f"unknown prim op: {op}")


def _require_arity(op: str, args: list[Value], n: int) -> None:
    if len(args) != n:
        raise EvalError(f"prim {op} arity mismatch")


def _int(val: Value) -> int:
    if not isinstance(val, IntVal):
        raise EvalError("expected int")
    return val.value


def _bool(val: Value) -> bool:
    if not isinstance(val, BoolVal):
        raise EvalError("expected bool")
    return val.value
