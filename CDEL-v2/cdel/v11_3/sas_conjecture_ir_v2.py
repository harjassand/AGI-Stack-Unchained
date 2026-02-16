"""SAS conjecture IR helpers (v11.2)."""

from __future__ import annotations

from typing import Any, Dict, List

from ..v1_7r.canon import CanonError, canon_bytes, sha256_prefixed

SCHEMA_VERSION = "sas_conjecture_ir_v2"
DOMAIN = "NAT_ARITH_EXT"

TYPES = {"Nat", "ListNat", "NatFn"}

NAT_OPS = {
    "Var",
    "NatLit",
    "Add",
    "Mul",
    "Pow",
    "Succ",
    "Pred",
    "Sub",
    "Gcd",
    "Mod",
    "ListLen",
    "ListSum",
    "ListProd",
}

LIST_OPS = {
    "Var",
    "ListNil",
    "ListCons",
    "ListAppend",
    "ListRange",
    "ListMap",
}

FN_OPS = {
    "FnSucc",
    "FnAddConst",
    "FnMulConst",
}

PROP_OPS = {
    "EqNat",
    "LeNat",
    "LtNat",
    "Dvd",
    "Prime",
    "EqListNat",
}

ALL_OPS = sorted(NAT_OPS | LIST_OPS | FN_OPS | PROP_OPS)


class ConjectureIRError(CanonError):
    pass


def _fail(reason: str) -> None:
    raise ConjectureIRError(reason)


def compute_conjecture_id(conjecture_ir: dict[str, Any]) -> str:
    payload = dict(conjecture_ir)
    payload.pop("conjecture_id", None)
    return sha256_prefixed(canon_bytes(payload))


def _require_exact_keys(obj: dict[str, Any], expected: set[str]) -> None:
    if set(obj.keys()) != expected:
        _fail("SCHEMA_INVALID")


def _validate_node(expr: dict[str, Any], var_types: dict[str, str]) -> None:
    if not isinstance(expr, dict):
        _fail("SCHEMA_INVALID")
    if "op" not in expr or "type" not in expr or "args" not in expr:
        _fail("SCHEMA_INVALID")
    op = expr.get("op")
    typ = expr.get("type")
    args = expr.get("args")
    if not isinstance(op, str) or not isinstance(typ, str):
        _fail("SCHEMA_INVALID")
    if typ not in TYPES:
        _fail("SCHEMA_INVALID")
    if not isinstance(args, list):
        _fail("SCHEMA_INVALID")

    if op == "Var":
        _require_exact_keys(expr, {"op", "type", "args", "name"})
        if typ not in TYPES:
            _fail("SCHEMA_INVALID")
        name = expr.get("name")
        if not isinstance(name, str):
            _fail("SCHEMA_INVALID")
        if name not in var_types:
            _fail("SCHEMA_INVALID")
        if var_types[name] != typ:
            _fail("SCHEMA_INVALID")
        if args:
            _fail("SCHEMA_INVALID")
        return

    if op == "NatLit":
        _require_exact_keys(expr, {"op", "type", "args", "lit"})
        if typ != "Nat":
            _fail("SCHEMA_INVALID")
        lit = expr.get("lit")
        if not isinstance(lit, int) or lit < 0:
            _fail("SCHEMA_INVALID")
        if args:
            _fail("SCHEMA_INVALID")
        return

    if op in {"FnSucc", "FnAddConst", "FnMulConst"}:
        if op == "FnSucc":
            _require_exact_keys(expr, {"op", "type", "args"})
        else:
            _require_exact_keys(expr, {"op", "type", "args", "c"})
        if typ != "NatFn":
            _fail("SCHEMA_INVALID")
        if args:
            _fail("SCHEMA_INVALID")
        if op in {"FnAddConst", "FnMulConst"}:
            c_val = expr.get("c")
            if not isinstance(c_val, int) or not (0 <= c_val <= 8):
                _fail("SCHEMA_INVALID")
        return

    signatures: dict[str, tuple[str, List[str]]] = {
        "Add": ("Nat", ["Nat", "Nat"]),
        "Mul": ("Nat", ["Nat", "Nat"]),
        "Pow": ("Nat", ["Nat", "Nat"]),
        "Succ": ("Nat", ["Nat"]),
        "Pred": ("Nat", ["Nat"]),
        "Sub": ("Nat", ["Nat", "Nat"]),
        "Gcd": ("Nat", ["Nat", "Nat"]),
        "Mod": ("Nat", ["Nat", "Nat"]),
        "ListLen": ("Nat", ["ListNat"]),
        "ListSum": ("Nat", ["ListNat"]),
        "ListProd": ("Nat", ["ListNat"]),
        "ListNil": ("ListNat", []),
        "ListCons": ("ListNat", ["Nat", "ListNat"]),
        "ListAppend": ("ListNat", ["ListNat", "ListNat"]),
        "ListRange": ("ListNat", ["Nat"]),
        "ListMap": ("ListNat", ["NatFn", "ListNat"]),
    }

    if op not in signatures:
        _fail("SCHEMA_INVALID")
    _require_exact_keys(expr, {"op", "type", "args"})
    expected_type, arg_types = signatures[op]
    if typ != expected_type:
        _fail("SCHEMA_INVALID")
    if len(args) != len(arg_types):
        _fail("SCHEMA_INVALID")
    for arg, expected in zip(args, arg_types):
        if not isinstance(arg, dict):
            _fail("SCHEMA_INVALID")
        if arg.get("type") != expected:
            _fail("SCHEMA_INVALID")
        _validate_node(arg, var_types)


def _validate_prop(prop: dict[str, Any], var_types: dict[str, str]) -> None:
    if not isinstance(prop, dict):
        _fail("SCHEMA_INVALID")
    _require_exact_keys(prop, {"op", "args"})
    op = prop.get("op")
    args = prop.get("args")
    if not isinstance(op, str) or not isinstance(args, list):
        _fail("SCHEMA_INVALID")
    if op not in PROP_OPS:
        _fail("SCHEMA_INVALID")

    if op in {"EqNat", "LeNat", "LtNat", "Dvd"}:
        if len(args) != 2:
            _fail("SCHEMA_INVALID")
        for arg in args:
            if not isinstance(arg, dict) or arg.get("type") != "Nat":
                _fail("SCHEMA_INVALID")
            _validate_node(arg, var_types)
        return
    if op == "Prime":
        if len(args) != 1:
            _fail("SCHEMA_INVALID")
        arg = args[0]
        if not isinstance(arg, dict) or arg.get("type") != "Nat":
            _fail("SCHEMA_INVALID")
        _validate_node(arg, var_types)
        return
    if op == "EqListNat":
        if len(args) != 2:
            _fail("SCHEMA_INVALID")
        for arg in args:
            if not isinstance(arg, dict) or arg.get("type") != "ListNat":
                _fail("SCHEMA_INVALID")
            _validate_node(arg, var_types)
        return

    _fail("SCHEMA_INVALID")


def validate_conjecture_ir(conjecture_ir: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(conjecture_ir, dict):
        _fail("SCHEMA_INVALID")
    expected_keys = {"schema_version", "conjecture_id", "domain", "vars", "goal"}
    if set(conjecture_ir.keys()) != expected_keys:
        _fail("SCHEMA_INVALID")
    if conjecture_ir.get("schema_version") != SCHEMA_VERSION:
        _fail("SCHEMA_INVALID")
    if conjecture_ir.get("domain") != DOMAIN:
        _fail("SCHEMA_INVALID")

    vars_list = conjecture_ir.get("vars")
    if not isinstance(vars_list, list):
        _fail("SCHEMA_INVALID")
    var_types: dict[str, str] = {}
    for item in vars_list:
        if not isinstance(item, dict):
            _fail("SCHEMA_INVALID")
        if set(item.keys()) != {"name", "type"}:
            _fail("SCHEMA_INVALID")
        name = item.get("name")
        vtype = item.get("type")
        if not isinstance(name, str) or not isinstance(vtype, str):
            _fail("SCHEMA_INVALID")
        if vtype not in TYPES:
            _fail("SCHEMA_INVALID")
        var_types[name] = vtype

    goal = conjecture_ir.get("goal")
    if not isinstance(goal, dict):
        _fail("SCHEMA_INVALID")
    _validate_prop(goal, var_types)

    expected = compute_conjecture_id(conjecture_ir)
    if conjecture_ir.get("conjecture_id") != expected:
        _fail("CONJECTURE_ID_MISMATCH")
    return conjecture_ir


def _normalize_term_for_fingerprint(expr: dict[str, Any], var_map: dict[str, str]) -> dict[str, Any]:
    op = expr.get("op")
    if op == "Var":
        name = str(expr.get("name"))
        return {"op": "Var", "type": expr.get("type"), "args": [], "name": var_map.get(name, name)}
    if op == "NatLit":
        return {"op": "NatLit", "type": "Nat", "args": [], "lit": 0}
    if op in {"FnSucc", "FnAddConst", "FnMulConst"}:
        node = {"op": op, "type": "NatFn", "args": []}
        if op in {"FnAddConst", "FnMulConst"}:
            node["c"] = 0
        return node
    args = expr.get("args") or []
    return {
        "op": op,
        "type": expr.get("type"),
        "args": [_normalize_term_for_fingerprint(arg, var_map) for arg in args],
    }


def _normalize_prop_for_fingerprint(prop: dict[str, Any], var_map: dict[str, str]) -> dict[str, Any]:
    return {
        "op": prop.get("op"),
        "args": [_normalize_term_for_fingerprint(arg, var_map) for arg in (prop.get("args") or [])],
    }


def compute_fingerprint(conjecture_ir: dict[str, Any]) -> dict[str, Any]:
    vars_list = conjecture_ir.get("vars") or []
    var_map: dict[str, str] = {}
    nat_idx = 0
    list_idx = 0
    fn_idx = 0
    norm_vars: list[dict[str, Any]] = []
    for item in vars_list:
        name = str(item.get("name"))
        vtype = str(item.get("type"))
        if vtype == "Nat":
            new_name = f"n{nat_idx}"
            nat_idx += 1
        elif vtype == "ListNat":
            new_name = f"xs{list_idx}"
            list_idx += 1
        else:
            new_name = f"f{fn_idx}"
            fn_idx += 1
        var_map[name] = new_name
        norm_vars.append({"name": new_name, "type": vtype})

    goal = _normalize_prop_for_fingerprint(conjecture_ir.get("goal"), var_map)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "domain": DOMAIN,
        "vars": norm_vars,
        "goal": goal,
    }
    fingerprint_hash = sha256_prefixed(canon_bytes(payload))
    return {
        "schema_version": "sas_conjecture_fingerprint_v2",
        "conjecture_id": compute_conjecture_id(conjecture_ir),
        "fingerprint_hash": fingerprint_hash,
    }


def _term_node_count(expr: dict[str, Any]) -> int:
    args = expr.get("args") or []
    total = 1
    for arg in args:
        total += _term_node_count(arg)
    return total


def _term_depth(expr: dict[str, Any]) -> int:
    args = expr.get("args") or []
    if not args:
        return 1
    return 1 + max(_term_depth(arg) for arg in args)


def _prop_node_count(prop: dict[str, Any]) -> int:
    args = prop.get("args") or []
    total = 1
    for arg in args:
        total += _term_node_count(arg)
    return total


def _prop_depth(prop: dict[str, Any]) -> int:
    args = prop.get("args") or []
    if not args:
        return 1
    return 1 + max(_term_depth(arg) for arg in args)


def _count_ops_term(expr: dict[str, Any], counts: dict[str, int]) -> None:
    op = expr.get("op")
    if isinstance(op, str) and op in counts:
        counts[op] += 1
    for arg in expr.get("args") or []:
        _count_ops_term(arg, counts)


def _count_ops_prop(prop: dict[str, Any], counts: dict[str, int]) -> None:
    op = prop.get("op")
    if isinstance(op, str) and op in counts:
        counts[op] += 1
    for arg in prop.get("args") or []:
        _count_ops_term(arg, counts)


def compute_metrics(conjecture_ir: dict[str, Any]) -> dict[str, Any]:
    goal = conjecture_ir.get("goal") or {}
    counts = {op: 0 for op in ALL_OPS}
    _count_ops_prop(goal, counts)
    return {
        "node_count": int(_prop_node_count(goal)),
        "binder_count": int(len(conjecture_ir.get("vars") or [])),
        "depth": int(_prop_depth(goal)),
        "op_counts": counts,
    }


def _render_term(expr: dict[str, Any]) -> str:
    op = expr.get("op")
    if op == "Var":
        return str(expr.get("name"))
    if op == "NatLit":
        return str(int(expr.get("lit", 0)))
    if op == "Add":
        a, b = expr.get("args") or [None, None]
        return f"({_render_term(a)} + {_render_term(b)})"
    if op == "Mul":
        a, b = expr.get("args") or [None, None]
        return f"({_render_term(a)} * {_render_term(b)})"
    if op == "Pow":
        a, b = expr.get("args") or [None, None]
        return f"({_render_term(a)} ^ {_render_term(b)})"
    if op == "Gcd":
        a, b = expr.get("args") or [None, None]
        return f"(Nat.gcd {_render_term(a)} {_render_term(b)})"
    if op == "Mod":
        a, b = expr.get("args") or [None, None]
        return f"({_render_term(a)} % {_render_term(b)})"
    if op == "Sub":
        a, b = expr.get("args") or [None, None]
        return f"({_render_term(a)} - {_render_term(b)})"
    if op == "Succ":
        a = (expr.get("args") or [None])[0]
        return f"(Nat.succ {_render_term(a)})"
    if op == "Pred":
        a = (expr.get("args") or [None])[0]
        return f"(Nat.pred {_render_term(a)})"
    if op == "ListNil":
        return "([] : List Nat)"
    if op == "ListCons":
        h, t = expr.get("args") or [None, None]
        return f"({_render_term(h)} :: {_render_term(t)})"
    if op == "ListAppend":
        a, b = expr.get("args") or [None, None]
        return f"({_render_term(a)} ++ {_render_term(b)})"
    if op == "ListRange":
        a = (expr.get("args") or [None])[0]
        return f"(List.range {_render_term(a)})"
    if op == "ListLen":
        xs = (expr.get("args") or [None])[0]
        return f"(List.length {_render_term(xs)})"
    if op == "ListSum":
        xs = (expr.get("args") or [None])[0]
        return f"(List.sum {_render_term(xs)})"
    if op == "ListProd":
        xs = (expr.get("args") or [None])[0]
        return f"(List.foldl (fun acc x => acc * x) 1 {_render_term(xs)})"
    if op == "ListMap":
        fn_node, xs = expr.get("args") or [None, None]
        fn_op = fn_node.get("op") if isinstance(fn_node, dict) else None
        if fn_op == "FnSucc":
            fn_txt = "Nat.succ"
        elif fn_op == "FnAddConst":
            c_val = int(fn_node.get("c", 0))
            fn_txt = f"(fun x => x + {c_val})"
        elif fn_op == "FnMulConst":
            c_val = int(fn_node.get("c", 0))
            fn_txt = f"(fun x => x * {c_val})"
        else:
            fn_txt = "Nat.succ"
        return f"(List.map {fn_txt} {_render_term(xs)})"
    return "0"


def _render_prop(prop: dict[str, Any]) -> str:
    op = prop.get("op")
    args = prop.get("args") or []
    if op == "EqNat":
        return f"{_render_term(args[0])} = {_render_term(args[1])}"
    if op == "LeNat":
        return f"{_render_term(args[0])} ≤ {_render_term(args[1])}"
    if op == "LtNat":
        return f"{_render_term(args[0])} < {_render_term(args[1])}"
    if op == "Dvd":
        return f"{_render_term(args[0])} ∣ {_render_term(args[1])}"
    if op == "Prime":
        return f"Nat.Prime {_render_term(args[0])}"
    if op == "EqListNat":
        return f"{_render_term(args[0])} = {_render_term(args[1])}"
    return "False"


def render_statement(conjecture_ir: dict[str, Any]) -> str:
    vars_list = conjecture_ir.get("vars") or []
    binders_parts = []
    for item in vars_list:
        vtype = item.get("type")
        if vtype == "Nat":
            binders_parts.append(f"({item.get('name')} : Nat)")
        elif vtype == "ListNat":
            binders_parts.append(f"({item.get('name')} : List Nat)")
        else:
            binders_parts.append(f"({item.get('name')} : Nat → Nat)")
    binders = " ".join(binders_parts)
    goal_expr = _render_prop(conjecture_ir.get("goal"))
    lines = [
        "import Std",
        "open Nat",
        "",
        f"example {binders} : {goal_expr} :=",
    ]
    return "\n".join(lines)


__all__ = [
    "compute_conjecture_id",
    "validate_conjecture_ir",
    "compute_fingerprint",
    "compute_metrics",
    "render_statement",
    "ConjectureIRError",
    "ALL_OPS",
]
