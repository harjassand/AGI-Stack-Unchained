"""Core AST types for the CDEL kernel."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from cdel.kernel.types import Type


class Term:
    pass


@dataclass(frozen=True)
class Var(Term):
    idx: int


@dataclass(frozen=True)
class Sym(Term):
    name: str


@dataclass(frozen=True)
class IntLit(Term):
    value: int


@dataclass(frozen=True)
class BoolLit(Term):
    value: bool


@dataclass(frozen=True)
class Nil(Term):
    pass


@dataclass(frozen=True)
class Cons(Term):
    head: Term
    tail: Term


@dataclass(frozen=True)
class OptionNone(Term):
    pass


@dataclass(frozen=True)
class OptionSome(Term):
    value: Term


@dataclass(frozen=True)
class MatchOption(Term):
    scrutinee: Term
    none_case: Term
    some_body: Term


@dataclass(frozen=True)
class Pair(Term):
    left: Term
    right: Term


@dataclass(frozen=True)
class Fst(Term):
    pair: Term


@dataclass(frozen=True)
class Snd(Term):
    pair: Term


@dataclass(frozen=True)
class If(Term):
    cond: Term
    then: Term
    els: Term


@dataclass(frozen=True)
class App(Term):
    fn: Term
    args: tuple[Term, ...]


@dataclass(frozen=True)
class Prim(Term):
    op: str
    args: tuple[Term, ...]


@dataclass(frozen=True)
class MatchList(Term):
    scrutinee: Term
    nil_case: Term
    cons_body: Term


@dataclass(frozen=True)
class Param:
    name: str
    typ: Type


@dataclass(frozen=True)
class Termination:
    kind: str
    decreases_param: Optional[str]


@dataclass(frozen=True)
class Definition:
    name: str
    params: tuple[Param, ...]
    ret_type: Type
    body: Term
    termination: Termination
