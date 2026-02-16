"""Cost model helpers."""

from __future__ import annotations

from cdel.kernel.ast import (
    App,
    BoolLit,
    Cons,
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
from cdel.kernel.types import BoolType, FunType, IntType, ListType, OptionType, PairType, Type


def count_term_nodes(term: Term) -> int:
    if isinstance(term, (Var, Sym, IntLit, BoolLit, Nil, OptionNone)):
        return 1
    if isinstance(term, OptionSome):
        return 1 + count_term_nodes(term.value)
    if isinstance(term, Cons):
        return 1 + count_term_nodes(term.head) + count_term_nodes(term.tail)
    if isinstance(term, Pair):
        return 1 + count_term_nodes(term.left) + count_term_nodes(term.right)
    if isinstance(term, (Fst, Snd)):
        return 1 + count_term_nodes(term.pair)
    if isinstance(term, If):
        return 1 + count_term_nodes(term.cond) + count_term_nodes(term.then) + count_term_nodes(term.els)
    if isinstance(term, App):
        return 1 + count_term_nodes(term.fn) + sum(count_term_nodes(arg) for arg in term.args)
    if isinstance(term, Prim):
        return 1 + sum(count_term_nodes(arg) for arg in term.args)
    if isinstance(term, MatchList):
        return 1 + count_term_nodes(term.scrutinee) + count_term_nodes(term.nil_case) + count_term_nodes(term.cons_body)
    if isinstance(term, MatchOption):
        return 1 + count_term_nodes(term.scrutinee) + count_term_nodes(term.none_case) + count_term_nodes(term.some_body)
    return 1


def count_type_nodes(typ: Type) -> int:
    if isinstance(typ, (IntType, BoolType)):
        return 1
    if isinstance(typ, ListType):
        return 1 + count_type_nodes(typ.elem)
    if isinstance(typ, OptionType):
        return 1 + count_type_nodes(typ.elem)
    if isinstance(typ, PairType):
        return 1 + count_type_nodes(typ.left) + count_type_nodes(typ.right)
    if isinstance(typ, FunType):
        return 1 + sum(count_type_nodes(arg) for arg in typ.args) + count_type_nodes(typ.ret)
    return 1
