"""Structural recursion checker."""

from __future__ import annotations

from cdel.kernel.ast import (
    App,
    Cons,
    Definition,
    Fst,
    If,
    MatchList,
    MatchOption,
    OptionSome,
    Pair,
    Prim,
    Snd,
    Sym,
    Term,
    Var,
)


class TerminationError(Exception):
    pass


def check_termination(defn: Definition) -> None:
    dec_param = defn.termination.decreases_param
    kind = defn.termination.kind
    if dec_param is None:
        if _has_recursive_call(defn):
            raise TerminationError("recursive definition missing decreases_param")
        return
    if kind != "structural":
        raise TerminationError("only structural termination is supported")
    try:
        dec_pos = [p.name for p in defn.params].index(dec_param)
    except ValueError as exc:
        raise TerminationError("decreases_param is not a parameter") from exc
    dec_idx = len(defn.params) - 1 - dec_pos
    found_recursive = False

    def shift(idx: int | None, delta: int) -> int | None:
        if idx is None:
            return None
        return idx + delta

    def walk(term: Term, dec_idx_local: int, allowed_tail_idx: int | None) -> None:
        nonlocal found_recursive
        if isinstance(term, App) and isinstance(term.fn, Sym) and term.fn.name == defn.name:
            found_recursive = True
            if allowed_tail_idx is None:
                raise TerminationError("recursive call must be under structural match")
            if dec_pos >= len(term.args):
                raise TerminationError("recursive call arity mismatch")
            dec_arg = term.args[dec_pos]
            if not isinstance(dec_arg, Var) or dec_arg.idx != allowed_tail_idx:
                raise TerminationError("recursive call does not use structural tail")
        if isinstance(term, MatchList):
            is_structural_match = isinstance(term.scrutinee, Var) and term.scrutinee.idx == dec_idx_local
            walk(term.nil_case, dec_idx_local, allowed_tail_idx)
            next_dec_idx = dec_idx_local + 2
            if is_structural_match:
                walk(term.cons_body, next_dec_idx, 0)
            else:
                walk(term.cons_body, next_dec_idx, shift(allowed_tail_idx, 2))
            return
        if isinstance(term, MatchOption):
            walk(term.scrutinee, dec_idx_local, allowed_tail_idx)
            walk(term.none_case, dec_idx_local, allowed_tail_idx)
            walk(term.some_body, dec_idx_local + 1, shift(allowed_tail_idx, 1))
            return
        if isinstance(term, If):
            walk(term.cond, dec_idx_local, allowed_tail_idx)
            walk(term.then, dec_idx_local, allowed_tail_idx)
            walk(term.els, dec_idx_local, allowed_tail_idx)
            return
        if isinstance(term, Cons):
            walk(term.head, dec_idx_local, allowed_tail_idx)
            walk(term.tail, dec_idx_local, allowed_tail_idx)
            return
        if isinstance(term, OptionSome):
            walk(term.value, dec_idx_local, allowed_tail_idx)
            return
        if isinstance(term, Pair):
            walk(term.left, dec_idx_local, allowed_tail_idx)
            walk(term.right, dec_idx_local, allowed_tail_idx)
            return
        if isinstance(term, (Fst, Snd)):
            walk(term.pair, dec_idx_local, allowed_tail_idx)
            return
        if isinstance(term, Prim):
            for arg in term.args:
                walk(arg, dec_idx_local, allowed_tail_idx)
            return
        if isinstance(term, App):
            walk(term.fn, dec_idx_local, allowed_tail_idx)
            for arg in term.args:
                walk(arg, dec_idx_local, allowed_tail_idx)
            return
        if isinstance(term, Var):
            return
        if isinstance(term, Sym):
            return
        return

    walk(defn.body, dec_idx, None)
    if found_recursive and defn.termination.kind != "structural":
        raise TerminationError("recursive definition missing structural termination")


def _has_recursive_call(defn: Definition) -> bool:
    def walk(term: Term) -> bool:
        if isinstance(term, App) and isinstance(term.fn, Sym) and term.fn.name == defn.name:
            return True
        if isinstance(term, MatchList):
            return walk(term.nil_case) or walk(term.cons_body) or walk(term.scrutinee)
        if isinstance(term, MatchOption):
            return walk(term.scrutinee) or walk(term.none_case) or walk(term.some_body)
        if isinstance(term, If):
            return walk(term.cond) or walk(term.then) or walk(term.els)
        if isinstance(term, Cons):
            return walk(term.head) or walk(term.tail)
        if isinstance(term, OptionSome):
            return walk(term.value)
        if isinstance(term, Pair):
            return walk(term.left) or walk(term.right)
        if isinstance(term, (Fst, Snd)):
            return walk(term.pair)
        if isinstance(term, Prim):
            return any(walk(arg) for arg in term.args)
        if isinstance(term, App):
            return walk(term.fn) or any(walk(arg) for arg in term.args)
        return False

    return walk(defn.body)
