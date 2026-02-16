"""Type definitions and normalization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


class Type:
    pass


@dataclass(frozen=True)
class IntType(Type):
    pass


@dataclass(frozen=True)
class BoolType(Type):
    pass


@dataclass(frozen=True)
class ListType(Type):
    elem: Type


@dataclass(frozen=True)
class OptionType(Type):
    elem: Type


@dataclass(frozen=True)
class PairType(Type):
    left: Type
    right: Type


@dataclass(frozen=True)
class FunType(Type):
    args: tuple[Type, ...]
    ret: Type


INT = IntType()
BOOL = BoolType()


def type_from_json(obj: dict) -> Type:
    if not isinstance(obj, dict):
        raise ValueError("type must be an object")
    tag = obj.get("tag")
    if tag == "int":
        return INT
    if tag == "bool":
        return BOOL
    if tag == "list":
        return ListType(type_from_json(obj.get("of")))
    if tag == "option":
        return OptionType(type_from_json(obj.get("of")))
    if tag == "pair":
        return PairType(type_from_json(obj.get("left")), type_from_json(obj.get("right")))
    if tag == "fun":
        args = obj.get("args")
        if not isinstance(args, list) or not args:
            raise ValueError("fun args must be a non-empty list")
        ret = obj.get("ret")
        return FunType(tuple(type_from_json(t) for t in args), type_from_json(ret))
    raise ValueError(f"unknown type tag: {tag}")


def type_to_json(typ: Type) -> dict:
    if isinstance(typ, IntType):
        return {"tag": "int"}
    if isinstance(typ, BoolType):
        return {"tag": "bool"}
    if isinstance(typ, ListType):
        return {"tag": "list", "of": type_to_json(typ.elem)}
    if isinstance(typ, OptionType):
        return {"tag": "option", "of": type_to_json(typ.elem)}
    if isinstance(typ, PairType):
        return {"tag": "pair", "left": type_to_json(typ.left), "right": type_to_json(typ.right)}
    if isinstance(typ, FunType):
        return {"tag": "fun", "args": [type_to_json(t) for t in typ.args], "ret": type_to_json(typ.ret)}
    raise ValueError(f"unsupported type: {typ}")


def type_norm(typ: Type) -> str:
    return _type_norm_prec(typ, 0)


def _type_norm_prec(typ: Type, prec: int) -> str:
    if isinstance(typ, IntType):
        return "Int"
    if isinstance(typ, BoolType):
        return "Bool"
    if isinstance(typ, ListType):
        return f"List[{_type_norm_prec(typ.elem, 0)}]"
    if isinstance(typ, OptionType):
        return f"Option[{_type_norm_prec(typ.elem, 0)}]"
    if isinstance(typ, PairType):
        left = _type_norm_prec(typ.left, 0)
        right = _type_norm_prec(typ.right, 0)
        return f"Pair[{left},{right}]"
    if isinstance(typ, FunType):
        parts: list[str] = []
        for arg in typ.args:
            part = _type_norm_prec(arg, 1)
            parts.append(part)
        ret = _type_norm_prec(typ.ret, 0)
        text = " -> ".join(parts + [ret])
        if prec > 0:
            return f"({text})"
        return text
    raise ValueError(f"unsupported type: {typ}")


def ensure_type(typ: Type, expected: Type, context: str) -> None:
    if typ != expected:
        raise TypeError(f"type mismatch in {context}: {type_norm(typ)} != {type_norm(expected)}")


def is_fun_type(typ: Type) -> bool:
    return isinstance(typ, FunType)


def fun_type_from_params(params: Iterable[Type], ret: Type) -> FunType:
    args = tuple(params)
    if not args:
        return FunType(tuple(), ret)
    return FunType(args, ret)
