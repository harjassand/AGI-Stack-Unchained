"""SAS conjecture IR helpers (v11.3)."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ..v1_7r.canon import CanonError, canon_bytes, sha256_prefixed

SCHEMA_VERSION = "sas_conjecture_ir_v3"
DOMAIN = "COMB_STRUCT_V1"

TYPES = {"Nat", "LNat", "NatFn"}

NAT_OPS = {
    "Var",
    "NatLit",
    "Add",
    "Mul",
    "Succ",
    "Len",
    "Sum",
}

LNAT_OPS = {
    "Var",
    "Nil",
    "Cons",
    "Append",
    "Rev",
    "Map",
    "Range",
    "Insert",
    "Sort",
}

FN_OPS = {
    "FnId",
    "FnAddConst",
    "FnMulConst",
}

PROP_OPS = {
    "EqNat",
    "EqLNat",
    "LeNat",
    "And",
    "Or",
    "Imp",
    "Sorted",
}

REC_OPS = {"Append", "Rev", "Map", "Range", "Insert", "Sort", "Sorted"}

ALL_OPS = sorted(NAT_OPS | LNAT_OPS | FN_OPS | PROP_OPS)


class ConjectureIRError(CanonError):
    pass


def _fail(reason: str) -> None:
    raise ConjectureIRError(reason)


def _require_exact_keys(obj: dict[str, Any], expected: set[str]) -> None:
    keys = set(obj.keys())
    if keys == expected:
        return
    if keys == expected | {"x-meta"}:
        return
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

    if op in {"FnId", "FnAddConst", "FnMulConst"}:
        if op == "FnId":
            _require_exact_keys(expr, {"op", "type", "args"})
        else:
            _require_exact_keys(expr, {"op", "type", "args", "c"})
        if typ != "NatFn":
            _fail("SCHEMA_INVALID")
        if args:
            _fail("SCHEMA_INVALID")
        if op in {"FnAddConst", "FnMulConst"}:
            c_val = expr.get("c")
            if not isinstance(c_val, int) or c_val not in {0, 1, 2, 3}:
                _fail("SCHEMA_INVALID")
        return

    signatures: dict[str, tuple[str, List[str]]] = {
        "Add": ("Nat", ["Nat", "Nat"]),
        "Mul": ("Nat", ["Nat", "Nat"]),
        "Succ": ("Nat", ["Nat"]),
        "Len": ("Nat", ["LNat"]),
        "Sum": ("Nat", ["LNat"]),
        "Nil": ("LNat", []),
        "Cons": ("LNat", ["Nat", "LNat"]),
        "Append": ("LNat", ["LNat", "LNat"]),
        "Rev": ("LNat", ["LNat"]),
        "Map": ("LNat", ["NatFn", "LNat"]),
        "Range": ("LNat", ["Nat"]),
        "Insert": ("LNat", ["Nat", "LNat"]),
        "Sort": ("LNat", ["LNat"]),
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

    if op in {"EqNat", "LeNat"}:
        if len(args) != 2:
            _fail("SCHEMA_INVALID")
        for arg in args:
            if not isinstance(arg, dict) or arg.get("type") != "Nat":
                _fail("SCHEMA_INVALID")
            _validate_node(arg, var_types)
        return

    if op == "EqLNat":
        if len(args) != 2:
            _fail("SCHEMA_INVALID")
        for arg in args:
            if not isinstance(arg, dict) or arg.get("type") != "LNat":
                _fail("SCHEMA_INVALID")
            _validate_node(arg, var_types)
        return

    if op in {"And", "Or", "Imp"}:
        if len(args) != 2:
            _fail("SCHEMA_INVALID")
        for arg in args:
            if not isinstance(arg, dict):
                _fail("SCHEMA_INVALID")
            _validate_prop(arg, var_types)
        return

    if op == "Sorted":
        if len(args) != 1:
            _fail("SCHEMA_INVALID")
        arg = args[0]
        if not isinstance(arg, dict) or arg.get("type") != "LNat":
            _fail("SCHEMA_INVALID")
        _validate_node(arg, var_types)
        return

    _fail("SCHEMA_INVALID")


def _validate_metrics(metrics: dict[str, Any]) -> None:
    if not isinstance(metrics, dict):
        _fail("SCHEMA_INVALID")
    required = {"binder_count", "depth", "node_count", "op_counts", "has_lnat", "has_rec_op"}
    if set(metrics.keys()) != required:
        _fail("SCHEMA_INVALID")
    if not isinstance(metrics.get("op_counts"), dict):
        _fail("SCHEMA_INVALID")
    for key in ["binder_count", "depth", "node_count"]:
        if not isinstance(metrics.get(key), int):
            _fail("SCHEMA_INVALID")
    if not isinstance(metrics.get("has_lnat"), bool) or not isinstance(metrics.get("has_rec_op"), bool):
        _fail("SCHEMA_INVALID")


def validate_conjecture_ir(conjecture_ir: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(conjecture_ir, dict):
        _fail("SCHEMA_INVALID")
    expected_keys = {"schema_version", "conjecture_id", "fingerprint_hash", "domain", "vars", "goal", "metrics"}
    _require_exact_keys(conjecture_ir, expected_keys)
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

    _validate_metrics(conjecture_ir.get("metrics"))

    fp_hash = compute_fingerprint_hash(conjecture_ir)
    if conjecture_ir.get("fingerprint_hash") != fp_hash:
        _fail("CONJECTURE_FINGERPRINT_MISMATCH")
    if conjecture_ir.get("conjecture_id") != fp_hash:
        _fail("CONJECTURE_ID_MISMATCH")
    return conjecture_ir


def _normalize_term_for_fingerprint(expr: dict[str, Any], var_map: dict[str, str]) -> dict[str, Any]:
    op = expr.get("op")
    if op == "Var":
        name = str(expr.get("name"))
        return {"op": "Var", "type": expr.get("type"), "args": [], "name": var_map.get(name, name)}
    if op == "NatLit":
        return {"op": "NatLit", "type": "Nat", "args": [], "lit": int(expr.get("lit", 0))}
    if op in {"FnId", "FnAddConst", "FnMulConst"}:
        node = {"op": op, "type": "NatFn", "args": []}
        if op in {"FnAddConst", "FnMulConst"}:
            node["c"] = int(expr.get("c", 0))
        return node
    args = expr.get("args") or []
    return {
        "op": op,
        "type": expr.get("type"),
        "args": [_normalize_term_for_fingerprint(arg, var_map) for arg in args],
    }


def _normalize_prop_for_fingerprint(prop: dict[str, Any], var_map: dict[str, str]) -> dict[str, Any]:
    op = prop.get("op")
    args = prop.get("args") or []
    if op in {"And", "Or", "Imp"}:
        return {"op": op, "args": [_normalize_prop_for_fingerprint(arg, var_map) for arg in args]}
    return {"op": op, "args": [_normalize_term_for_fingerprint(arg, var_map) for arg in args]}


def compute_fingerprint_hash(conjecture_ir: dict[str, Any]) -> str:
    vars_list = conjecture_ir.get("vars") or []
    var_map: dict[str, str] = {}
    nat_idx = 0
    lnat_idx = 0
    fn_idx = 0
    norm_vars: list[dict[str, Any]] = []
    for item in vars_list:
        name = str(item.get("name"))
        vtype = str(item.get("type"))
        if vtype == "Nat":
            new_name = f"n{nat_idx}"
            nat_idx += 1
        elif vtype == "LNat":
            new_name = f"xs{lnat_idx}"
            lnat_idx += 1
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
    return sha256_prefixed(canon_bytes(payload))


def compute_conjecture_id(conjecture_ir: dict[str, Any]) -> str:
    return compute_fingerprint_hash(conjecture_ir)


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
    op = prop.get("op")
    if op in {"And", "Or", "Imp"}:
        for arg in args:
            total += _prop_node_count(arg)
        return total
    for arg in args:
        total += _term_node_count(arg)
    return total


def _prop_depth(prop: dict[str, Any]) -> int:
    args = prop.get("args") or []
    op = prop.get("op")
    if not args:
        return 1
    if op in {"And", "Or", "Imp"}:
        return 1 + max(_prop_depth(arg) for arg in args)
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
    args = prop.get("args") or []
    if op in {"And", "Or", "Imp"}:
        for arg in args:
            _count_ops_prop(arg, counts)
    else:
        for arg in args:
            _count_ops_term(arg, counts)


def compute_metrics(conjecture_ir: dict[str, Any]) -> dict[str, Any]:
    goal = conjecture_ir.get("goal") or {}
    counts = {op: 0 for op in ALL_OPS}
    _count_ops_prop(goal, counts)
    vars_list = conjecture_ir.get("vars") or []
    has_lnat = any(item.get("type") == "LNat" for item in vars_list)
    has_rec_op = any(counts.get(op, 0) > 0 for op in REC_OPS)
    return {
        "node_count": int(_prop_node_count(goal)),
        "binder_count": int(len(vars_list)),
        "depth": int(_prop_depth(goal)),
        "op_counts": counts,
        "has_lnat": bool(has_lnat),
        "has_rec_op": bool(has_rec_op),
    }


def collect_used_binders(goal: dict[str, Any]) -> set[str]:
    used: set[str] = set()

    def _walk_term(term: dict[str, Any]) -> None:
        if term.get("op") == "Var":
            name = term.get("name")
            if isinstance(name, str):
                used.add(name)
        for arg in term.get("args") or []:
            if isinstance(arg, dict):
                _walk_term(arg)

    def _walk_prop(prop: dict[str, Any]) -> None:
        op = prop.get("op")
        args = prop.get("args") or []
        if op in {"And", "Or", "Imp"}:
            for arg in args:
                if isinstance(arg, dict):
                    _walk_prop(arg)
            return
        for arg in args:
            if isinstance(arg, dict):
                _walk_term(arg)

    _walk_prop(goal)
    return used


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
    if op == "Succ":
        a = (expr.get("args") or [None])[0]
        return f"(Nat.succ {_render_term(a)})"
    if op == "Len":
        xs = (expr.get("args") or [None])[0]
        return f"(llen {_render_term(xs)})"
    if op == "Sum":
        xs = (expr.get("args") or [None])[0]
        return f"(lsum {_render_term(xs)})"
    if op == "Nil":
        return "LNat.nil"
    if op == "Cons":
        h, t = expr.get("args") or [None, None]
        return f"(LNat.cons {_render_term(h)} {_render_term(t)})"
    if op == "Append":
        a, b = expr.get("args") or [None, None]
        return f"(lappend {_render_term(a)} {_render_term(b)})"
    if op == "Rev":
        xs = (expr.get("args") or [None])[0]
        return f"(lrev {_render_term(xs)})"
    if op == "Map":
        fn_node, xs = expr.get("args") or [None, None]
        return f"(lmap {_render_fn(fn_node)} {_render_term(xs)})"
    if op == "Range":
        n = (expr.get("args") or [None])[0]
        return f"(range {_render_term(n)})"
    if op == "Insert":
        a, xs = expr.get("args") or [None, None]
        return f"(linsert {_render_term(a)} {_render_term(xs)})"
    if op == "Sort":
        xs = (expr.get("args") or [None])[0]
        return f"(lsort {_render_term(xs)})"
    return "0"


def _render_fn(expr: dict[str, Any]) -> str:
    op = expr.get("op")
    if op == "Var":
        return str(expr.get("name"))
    if op == "FnId":
        return "(fun z => z)"
    if op == "FnAddConst":
        c_val = int(expr.get("c", 0))
        return f"(fun z => z + {c_val})"
    if op == "FnMulConst":
        c_val = int(expr.get("c", 0))
        return f"(fun z => z * {c_val})"
    return "(fun z => z)"


def _render_prop(prop: dict[str, Any]) -> str:
    op = prop.get("op")
    args = prop.get("args") or []
    if op == "EqNat":
        return f"{_render_term(args[0])} = {_render_term(args[1])}"
    if op == "EqLNat":
        return f"{_render_term(args[0])} = {_render_term(args[1])}"
    if op == "LeNat":
        return f"{_render_term(args[0])} <= {_render_term(args[1])}"
    if op == "And":
        return f"(And {_render_prop(args[0])} {_render_prop(args[1])})"
    if op == "Or":
        return f"(Or {_render_prop(args[0])} {_render_prop(args[1])})"
    if op == "Imp":
        return f"({_render_prop(args[0])} -> {_render_prop(args[1])})"
    if op == "Sorted":
        return f"(lsorted {_render_term(args[0])})"
    return "False"


def render_statement(conjecture_ir: dict[str, Any], *, preamble_text: str) -> str:
    vars_list = conjecture_ir.get("vars") or []
    binders_parts = []
    for item in vars_list:
        vtype = item.get("type")
        name = item.get("name")
        if vtype == "Nat":
            binders_parts.append(f"({name} : Nat)")
        elif vtype == "LNat":
            binders_parts.append(f"({name} : LNat)")
        else:
            binders_parts.append(f"({name} : Nat -> Nat)")
    binders = " ".join(binders_parts)
    goal_expr = _render_prop(conjecture_ir.get("goal"))
    preamble = preamble_text.rstrip("\n")
    lines = [preamble, "", f"example {binders} : {goal_expr} :="]
    return "\n".join(lines)


__all__ = [
    "compute_conjecture_id",
    "compute_fingerprint_hash",
    "validate_conjecture_ir",
    "compute_metrics",
    "render_statement",
    "collect_used_binders",
    "ConjectureIRError",
    "ALL_OPS",
    "REC_OPS",
]
