"""Enumerative generator baseline (minimal)."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
import json

from blake3 import blake3

from cdel.kernel.deps import collect_sym_refs, collect_sym_refs_in_specs
from cdel.kernel.eval import BoolVal, Evaluator, FunVal, IntVal, ListVal, OptionVal, PairVal, Value
from cdel.kernel.parse import parse_definition
from cdel.kernel.types import BOOL, INT, FunType, ListType, OptionType, PairType, Type, type_norm


@dataclass(frozen=True)
class TaskSpec:
    new_symbol: str
    typ: Type
    specs: list[dict]
    allowed_deps: list[str]


@dataclass(frozen=True)
class Candidate:
    definition: dict
    declared_deps: list[str]


class EnumGenerator:
    def __init__(
        self,
        max_size: int = 6,
        max_candidates: int = 300,
        step_limit: int = 2000,
        mode: str = "baseline",
        symbol_priority: list[str] | None = None,
    ) -> None:
        self.max_size = max_size
        self.max_candidates = max_candidates
        self.step_limit = step_limit
        self.mode = mode
        self.symbol_priority = symbol_priority or []
        self.last_stats: dict[str, int | None] = {}

    def generate(self, task: TaskSpec, env_symbols: dict[str, Type], env_defs: dict[str, object] | None = None) -> list[Candidate]:
        params = _params_for_type(task.typ)
        allowed = set(task.allowed_deps)
        filtered_symbols = {name: env_symbols[name] for name in env_symbols if name in allowed}
        fun_symbols = self._order_symbols(filtered_symbols)
        ret_type = task.typ.ret if isinstance(task.typ, FunType) else task.typ
        body_candidates = self._enumerate_bodies(task.new_symbol, ret_type, params, fun_symbols)
        candidates: list[Candidate] = []
        seen: set[tuple[str, int, str]] = set()
        env_defs = env_defs or {}
        sample_domain = _sample_domain(task, params, filtered_symbols)
        spec_refs = collect_sym_refs_in_specs(task.specs)
        stats: dict[str, int | None] = {
            "bodies_enumerated": 0,
            "deduped": 0,
            "output_fail": 0,
            "min_size": None,
            "max_size": None,
            "candidates_returned": 0,
        }
        for body in body_candidates:
            stats["bodies_enumerated"] += 1
            size = _term_size(body)
            if stats["min_size"] is None or size < stats["min_size"]:
                stats["min_size"] = size
            if stats["max_size"] is None or size > stats["max_size"]:
                stats["max_size"] = size
            defn = {
                "name": task.new_symbol,
                "params": params,
                "ret_type": _type_json(ret_type),
                "body": body,
                "termination": {
                    "kind": "structural",
                    "decreases_param": _find_decreases_param(params),
                },
            }
            output_hash = _output_hash(defn, env_defs, sample_domain, self.step_limit)
            if output_hash is None:
                stats["output_fail"] += 1
                continue
            key = (type_norm(task.typ), size, output_hash)
            if key in seen:
                stats["deduped"] += 1
                continue
            seen.add(key)
            deps = collect_sym_refs(body) | spec_refs
            deps = sorted(s for s in deps if s != task.new_symbol and s in allowed)
            candidates.append(Candidate(definition=defn, declared_deps=deps))
            if len(candidates) >= self.max_candidates:
                break
        stats["candidates_returned"] = len(candidates)
        self.last_stats = stats
        return candidates

    def _enumerate_bodies(self, symbol: str, typ: Type, params: list[dict], fun_symbols: list[tuple[str, Type]]) -> list[dict]:
        env_vars = [(p["name"], _type_from_json(p["type"])) for p in params]
        candidates: list[dict] = []
        dec_param = _find_decreases_param(params)
        if dec_param is not None:
            dec_info = next(p for p in params if p["name"] == dec_param)
            head_name = "h"
            tail_name = "t"
            base_terms = self._enumerate_terms(typ, env_vars, fun_symbols, 3)
            base_terms = _prioritize_base_terms(typ, base_terms)
            rec_call = _recursive_call(symbol, params, dec_param, tail_name)
            cons_env = [(head_name, _type_from_json(dec_info["type"]["of"])), (tail_name, _type_from_json(dec_info["type"]))] + env_vars
            step_terms = self._enumerate_terms(typ, cons_env, fun_symbols, self.max_size, extra=[rec_call])
            for base in base_terms:
                for step in step_terms:
                    candidates.append(
                        {
                            "tag": "match_list",
                            "scrutinee": {"tag": "var", "name": dec_param},
                            "nil_case": base,
                            "cons_case": {
                                "head_var": head_name,
                                "tail_var": tail_name,
                                "body": step,
                            },
                        }
                    )
                    if len(candidates) >= self.max_candidates:
                        return candidates
        # Non-recursive candidates
        candidates.extend(self._enumerate_terms(typ, env_vars, fun_symbols, self.max_size))
        return candidates

    def _order_symbols(self, symbols: dict[str, Type]) -> list[tuple[str, Type]]:
        if not self.symbol_priority:
            return [(name, symbols[name]) for name in sorted(symbols)]
        priority = {name: idx for idx, name in enumerate(self.symbol_priority)}
        return sorted(
            [(name, symbols[name]) for name in symbols],
            key=lambda item: (priority.get(item[0], len(priority)), item[0]),
        )

    def _enumerate_terms(
        self,
        typ: Type,
        env_vars: list[tuple[str, Type]],
        fun_symbols: list[tuple[str, Type]],
        max_size: int,
        extra: list[dict] | None = None,
    ) -> list[dict]:
        extra = extra or []
        results: list[dict] = []
        if self.mode == "reuse":
            for size in range(1, max_size + 1):
                for term in _app_terms_of_size(typ, env_vars, fun_symbols, size, extra, True):
                    results.append(term)
                    if len(results) >= self.max_candidates:
                        return results
        for size in range(1, max_size + 1):
            for term in _enum_terms_of_size(
                typ,
                env_vars,
                fun_symbols,
                size,
                extra,
                prefer_apps=False,
            ):
                results.append(term)
                if len(results) >= self.max_candidates:
                    return results
        return results


def _enum_terms_of_size(
    typ: Type,
    env_vars: list[tuple[str, Type]],
    fun_symbols: list[tuple[str, Type]],
    size: int,
    extra: list[dict],
    prefer_apps: bool,
) -> list[dict]:
    if size == 1:
        terms: list[dict] = list(extra)
        terms.extend(_base_terms(typ, env_vars, fun_symbols))
        return terms
    results: list[dict] = []
    if prefer_apps:
        results.extend(_app_terms_of_size(typ, env_vars, fun_symbols, size, extra, prefer_apps))
    if typ == INT:
        for op in ["add", "sub", "mul", "mod"]:
            for left_size in range(1, size - 1):
                right_size = size - 1 - left_size
                for a in _enum_terms_of_size(INT, env_vars, fun_symbols, left_size, extra, prefer_apps):
                    for b in _enum_terms_of_size(INT, env_vars, fun_symbols, right_size, extra, prefer_apps):
                        results.append({"tag": "prim", "op": op, "args": [a, b]})
    if typ == BOOL:
        for op in ["eq_int", "lt_int", "le_int"]:
            for left_size in range(1, size - 1):
                right_size = size - 1 - left_size
                for a in _enum_terms_of_size(INT, env_vars, fun_symbols, left_size, extra, prefer_apps):
                    for b in _enum_terms_of_size(INT, env_vars, fun_symbols, right_size, extra, prefer_apps):
                        results.append({"tag": "prim", "op": op, "args": [a, b]})
        for op in ["and", "or"]:
            for left_size in range(1, size - 1):
                right_size = size - 1 - left_size
                for a in _enum_terms_of_size(BOOL, env_vars, fun_symbols, left_size, extra, prefer_apps):
                    for b in _enum_terms_of_size(BOOL, env_vars, fun_symbols, right_size, extra, prefer_apps):
                        results.append({"tag": "prim", "op": op, "args": [a, b]})
        for inner in _enum_terms_of_size(BOOL, env_vars, fun_symbols, size - 1, extra, prefer_apps):
            results.append({"tag": "prim", "op": "not", "args": [inner]})
    if isinstance(typ, ListType):
        if size == 2:
            for head in _enum_terms_of_size(typ.elem, env_vars, fun_symbols, 1, extra, prefer_apps):
                results.append({"tag": "cons", "head": head, "tail": {"tag": "nil"}})
    if isinstance(typ, OptionType):
        if size == 1:
            results.append({"tag": "none"})
        if size >= 2:
            inner_size = size - 1
            for inner in _enum_terms_of_size(typ.elem, env_vars, fun_symbols, inner_size, extra, prefer_apps):
                results.append({"tag": "some", "value": inner})
    if isinstance(typ, PairType):
        for left_size in range(1, size - 1):
            right_size = size - 1 - left_size
            if right_size < 1:
                continue
            for left in _enum_terms_of_size(typ.left, env_vars, fun_symbols, left_size, extra, prefer_apps):
                for right in _enum_terms_of_size(typ.right, env_vars, fun_symbols, right_size, extra, prefer_apps):
                    results.append({"tag": "pair", "left": left, "right": right})
    if size >= 3:
        for cond_size in range(1, size - 2):
            for then_size in range(1, size - 1 - cond_size):
                else_size = size - 1 - cond_size - then_size
                for cond in _enum_terms_of_size(BOOL, env_vars, fun_symbols, cond_size, extra, prefer_apps):
                    for t_then in _enum_terms_of_size(typ, env_vars, fun_symbols, then_size, extra, prefer_apps):
                        for t_else in _enum_terms_of_size(typ, env_vars, fun_symbols, else_size, extra, prefer_apps):
                            results.append({"tag": "if", "cond": cond, "then": t_then, "else": t_else})
    if not prefer_apps:
        results.extend(_app_terms_of_size(typ, env_vars, fun_symbols, size, extra, prefer_apps))
    if size >= 2:
        for pair_type in _pair_types_in_env(env_vars, fun_symbols):
            if pair_type.left == typ:
                for pair_term in _enum_terms_of_size(pair_type, env_vars, fun_symbols, size - 1, extra, prefer_apps):
                    results.append({"tag": "fst", "pair": pair_term})
            if pair_type.right == typ:
                for pair_term in _enum_terms_of_size(pair_type, env_vars, fun_symbols, size - 1, extra, prefer_apps):
                    results.append({"tag": "snd", "pair": pair_term})
    return results


def _app_terms_of_size(
    typ: Type,
    env_vars: list[tuple[str, Type]],
    fun_symbols: list[tuple[str, Type]],
    size: int,
    extra: list[dict],
    prefer_apps: bool,
) -> list[dict]:
    results: list[dict] = []
    for name, ftype in fun_symbols:
        if isinstance(ftype, FunType) and ftype.ret == typ:
            arg_sizes = _split_sizes(len(ftype.args), size - 1)
            for sizes in arg_sizes:
                arg_terms = []
                ok = True
                for arg_type, arg_size in zip(ftype.args, sizes):
                    terms = _enum_terms_of_size(arg_type, env_vars, fun_symbols, arg_size, extra, prefer_apps)
                    if not terms:
                        ok = False
                        break
                    arg_terms.append(terms)
                if not ok:
                    continue
                for combo in product(*arg_terms):
                    results.append({"tag": "app", "fn": {"tag": "sym", "name": name}, "args": list(combo)})
    return results


def _base_terms(typ: Type, env_vars: list[tuple[str, Type]], fun_symbols: list[tuple[str, Type]]) -> list[dict]:
    terms: list[dict] = []
    if typ == INT:
        for val in [-1, 0, 1, 2]:
            terms.append({"tag": "int", "value": val})
    if typ == BOOL:
        terms.append({"tag": "bool", "value": False})
        terms.append({"tag": "bool", "value": True})
    if isinstance(typ, ListType):
        terms.append({"tag": "nil"})
    if isinstance(typ, OptionType):
        terms.append({"tag": "none"})
    for name, vtype in env_vars:
        if vtype == typ:
            terms.append({"tag": "var", "name": name})
    for name, vtype in fun_symbols:
        if vtype == typ:
            terms.append({"tag": "sym", "name": name})
    return terms


def _prioritize_base_terms(typ: Type, terms: list[dict]) -> list[dict]:
    if typ != INT:
        return terms
    buckets = {0: [], 1: [], 2: [], 3: []}
    rest: list[dict] = []
    for term in terms:
        if term.get("tag") == "int":
            val = term.get("value")
            if val == 0:
                buckets[0].append(term)
                continue
            if val == 1:
                buckets[1].append(term)
                continue
            if val == -1:
                buckets[2].append(term)
                continue
            if val == 2:
                buckets[3].append(term)
                continue
        rest.append(term)
    return buckets[0] + buckets[1] + buckets[2] + buckets[3] + rest


def _recursive_call(symbol: str, params: list[dict], dec_param: str | None, tail_name: str) -> dict:
    args = []
    for param in params:
        name = param["name"]
        if dec_param is not None and name == dec_param:
            args.append({"tag": "var", "name": tail_name})
        else:
            args.append({"tag": "var", "name": name})
    return {"tag": "app", "fn": {"tag": "sym", "name": symbol}, "args": args}


def _params_for_type(typ: Type) -> list[dict]:
    if isinstance(typ, FunType):
        params = []
        for i, arg in enumerate(typ.args):
            params.append({"name": f"p{i}", "type": _type_json(arg)})
        return params
    return []


def _find_decreases_param(params: list[dict]) -> str | None:
    for param in params:
        if param.get("type", {}).get("tag") == "list":
            return param.get("name")
    return None


def _type_json(typ: Type) -> dict:
    if typ == INT:
        return {"tag": "int"}
    if typ == BOOL:
        return {"tag": "bool"}
    if isinstance(typ, ListType):
        return {"tag": "list", "of": _type_json(typ.elem)}
    if isinstance(typ, OptionType):
        return {"tag": "option", "of": _type_json(typ.elem)}
    if isinstance(typ, PairType):
        return {"tag": "pair", "left": _type_json(typ.left), "right": _type_json(typ.right)}
    if isinstance(typ, FunType):
        return {"tag": "fun", "args": [_type_json(t) for t in typ.args], "ret": _type_json(typ.ret)}
    raise ValueError("unsupported type")


def _type_from_json(obj: dict) -> Type:
    tag = obj.get("tag")
    if tag == "int":
        return INT
    if tag == "bool":
        return BOOL
    if tag == "list":
        return ListType(_type_from_json(obj.get("of")))
    if tag == "option":
        return OptionType(_type_from_json(obj.get("of")))
    if tag == "pair":
        return PairType(_type_from_json(obj.get("left")), _type_from_json(obj.get("right")))
    if tag == "fun":
        args = [_type_from_json(t) for t in obj.get("args")]
        return FunType(tuple(args), _type_from_json(obj.get("ret")))
    raise ValueError("unsupported type")


def _split_sizes(n: int, total: int) -> list[list[int]]:
    if n == 0:
        return [[]] if total == 0 else []
    if n == 1:
        return [[total]] if total >= 1 else []
    results: list[list[int]] = []
    for first in range(1, total - n + 2):
        for rest in _split_sizes(n - 1, total - first):
            results.append([first] + rest)
    return results


def _sample_domain(task: TaskSpec, params: list[dict], env_symbols: dict[str, Type]) -> list[list[Value]]:
    domain = _task_domain(task)
    param_types = [_type_from_json(p["type"]) for p in params]
    return [
        _domain_for_type(
            typ,
            domain["int_min"],
            domain["int_max"],
            domain["list_max_len"],
            domain["fun_symbols"],
            env_symbols,
        )
        for typ in param_types
    ]


def _task_domain(task: TaskSpec) -> dict:
    if task.specs:
        domain = task.specs[0].get("domain") or {}
        return {
            "int_min": int(domain.get("int_min", -1)),
            "int_max": int(domain.get("int_max", 1)),
            "list_max_len": int(domain.get("list_max_len", 2)),
            "fun_symbols": list(domain.get("fun_symbols") or []),
        }
    return {"int_min": -1, "int_max": 1, "list_max_len": 2, "fun_symbols": []}


def _domain_for_type(
    typ: Type,
    int_min: int,
    int_max: int,
    list_max_len: int,
    fun_symbols: list[str],
    env_symbols: dict[str, Type],
) -> list[Value]:
    if typ == INT:
        return [IntVal(i) for i in range(int_min, int_max + 1)]
    if typ == BOOL:
        return [BoolVal(False), BoolVal(True)]
    if isinstance(typ, ListType):
        elems = _domain_for_type(typ.elem, int_min, int_max, list_max_len, fun_symbols, env_symbols)
        return _list_domain(elems, list_max_len)
    if isinstance(typ, OptionType):
        elems = _domain_for_type(typ.elem, int_min, int_max, list_max_len, fun_symbols, env_symbols)
        values = [OptionVal(False, None)]
        values.extend(OptionVal(True, elem) for elem in elems)
        return values
    if isinstance(typ, PairType):
        left = _domain_for_type(typ.left, int_min, int_max, list_max_len, fun_symbols, env_symbols)
        right = _domain_for_type(typ.right, int_min, int_max, list_max_len, fun_symbols, env_symbols)
        return [PairVal(l, r) for l, r in product(left, right)]
    if isinstance(typ, FunType):
        values: list[Value] = []
        for name in sorted(fun_symbols):
            sym_type = env_symbols.get(name)
            if sym_type is None:
                continue
            if sym_type == typ:
                values.append(FunVal(name))
        return values
    return []


def _list_domain(elems: list[Value], max_len: int) -> list[ListVal]:
    lists: list[ListVal] = [ListVal(tuple())]
    if max_len <= 0:
        return lists
    for length in range(1, max_len + 1):
        for combo in product(elems, repeat=length):
            lists.append(ListVal(tuple(combo)))
    return lists


def _output_hash(defn_json: dict, env_defs: dict[str, object], sample_domain: list[list[Value]], step_limit: int) -> str | None:
    try:
        definition = parse_definition(defn_json)
    except Exception:
        return None
    defs = dict(env_defs)
    defs[definition.name] = definition
    outputs: list[object] = []
    for assignment in product(*sample_domain):
        env: list[Value] = []
        for value in assignment:
            env.insert(0, value)
        try:
            evaluator = Evaluator(step_limit)
            value = evaluator.eval_term(definition.body, env, defs)
        except Exception:
            return None
        outputs.append(_value_to_json(value))
    data = json.dumps(outputs, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return blake3(data).hexdigest()


def _value_to_json(value: Value) -> object:
    if isinstance(value, IntVal):
        return value.value
    if isinstance(value, BoolVal):
        return value.value
    if isinstance(value, ListVal):
        return [_value_to_json(v) for v in value.items]
    if isinstance(value, OptionVal):
        if not value.is_some:
            return {"option": "none"}
        return {"option": "some", "value": _value_to_json(value.value)}
    if isinstance(value, PairVal):
        return {"pair": [_value_to_json(value.left), _value_to_json(value.right)]}
    if isinstance(value, FunVal):
        return {"fun": value.name}
    return str(value)


def _term_size(node: dict) -> int:
    if not isinstance(node, dict):
        return 0
    tag = node.get("tag")
    if tag in {"int", "bool", "nil", "var", "sym"}:
        return 1
    if tag == "cons":
        return 1 + _term_size(node.get("head")) + _term_size(node.get("tail"))
    if tag == "if":
        return 1 + _term_size(node.get("cond")) + _term_size(node.get("then")) + _term_size(node.get("else"))
    if tag == "app":
        args = node.get("args") or []
        return 1 + _term_size(node.get("fn")) + sum(_term_size(arg) for arg in args)
    if tag == "prim":
        args = node.get("args") or []
        return 1 + sum(_term_size(arg) for arg in args)
    if tag == "match_list":
        cons_case = node.get("cons_case") or {}
        return (
            1
            + _term_size(node.get("scrutinee"))
            + _term_size(node.get("nil_case"))
            + _term_size(cons_case.get("body"))
        )
    if tag == "none":
        return 1
    if tag == "some":
        return 1 + _term_size(node.get("value"))
    if tag == "match_option":
        some_case = node.get("some_case") or {}
        return (
            1
            + _term_size(node.get("scrutinee"))
            + _term_size(node.get("none_case"))
            + _term_size(some_case.get("body"))
        )
    if tag == "pair":
        return 1 + _term_size(node.get("left")) + _term_size(node.get("right"))
    if tag in {"fst", "snd"}:
        return 1 + _term_size(node.get("pair"))
    return 1


def _pair_types_in_env(env_vars: list[tuple[str, Type]], fun_symbols: list[tuple[str, Type]]) -> list[PairType]:
    seen: list[PairType] = []
    for _, typ in env_vars:
        if isinstance(typ, PairType) and typ not in seen:
            seen.append(typ)
    for _, typ in fun_symbols:
        if isinstance(typ, PairType) and typ not in seen:
            seen.append(typ)
    return seen
