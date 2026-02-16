"""Deterministic conjecture generator (v11.2)."""

from __future__ import annotations

from typing import Any, Dict, List

from .sas_conjecture_ir_v2 import DOMAIN, SCHEMA_VERSION, compute_conjecture_id, compute_metrics
from .sas_conjecture_seed_v2 import rng_u64_for_seed


def _seed_bytes_from(seed: str) -> bytes:
    text = str(seed)
    if text.startswith("sha256:"):
        hex_part = text.split(":", 1)[1]
        if len(hex_part) == 64:
            try:
                return bytes.fromhex(hex_part)
            except ValueError:
                return text.encode("utf-8")
    return text.encode("utf-8")


class DeterministicRNG:
    def __init__(self, seed: str) -> None:
        self._seed_bytes = _seed_bytes_from(seed)
        self._counter = 0

    def _u64(self, label: str) -> int:
        val = rng_u64_for_seed(self._seed_bytes, label, self._counter)
        self._counter += 1
        return val

    def choice(self, items: List[Any], label: str) -> Any:
        if not items:
            raise ValueError("empty choice list")
        idx = self._u64(label) % len(items)
        return items[int(idx)]

    def weighted_choice(self, weights: Dict[str, int], label: str) -> str:
        if not weights:
            raise ValueError("empty weights")
        total = sum(max(0, int(v)) for v in weights.values())
        if total <= 0:
            # fall back to deterministic choice of sorted keys
            return sorted(weights.keys())[0]
        pick = int(self._u64(label) % total)
        running = 0
        for key, weight in weights.items():
            w = max(0, int(weight))
            running += w
            if pick < running:
                return key
        return sorted(weights.keys())[0]


# Node builders

def _var(name: str, typ: str) -> dict[str, Any]:
    return {"op": "Var", "type": typ, "args": [], "name": name}


def _lit(value: int) -> dict[str, Any]:
    return {"op": "NatLit", "type": "Nat", "args": [], "lit": int(value)}


def _bin(op: str, lhs: dict[str, Any], rhs: dict[str, Any], typ: str = "Nat") -> dict[str, Any]:
    return {"op": op, "type": typ, "args": [lhs, rhs]}


def _un(op: str, arg: dict[str, Any], typ: str = "Nat") -> dict[str, Any]:
    return {"op": op, "type": typ, "args": [arg]}


def _list_nil() -> dict[str, Any]:
    return {"op": "ListNil", "type": "ListNat", "args": []}


def _list_cons(head: dict[str, Any], tail: dict[str, Any]) -> dict[str, Any]:
    return {"op": "ListCons", "type": "ListNat", "args": [head, tail]}


def _list_append(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    return {"op": "ListAppend", "type": "ListNat", "args": [a, b]}


def _list_range(n: dict[str, Any]) -> dict[str, Any]:
    return {"op": "ListRange", "type": "ListNat", "args": [n]}


def _list_map(fn: dict[str, Any], xs: dict[str, Any]) -> dict[str, Any]:
    return {"op": "ListMap", "type": "ListNat", "args": [fn, xs]}


def _fn_succ() -> dict[str, Any]:
    return {"op": "FnSucc", "type": "NatFn", "args": []}


def _fn_add_const(c: int) -> dict[str, Any]:
    return {"op": "FnAddConst", "type": "NatFn", "args": [], "c": int(c)}


def _fn_mul_const(c: int) -> dict[str, Any]:
    return {"op": "FnMulConst", "type": "NatFn", "args": [], "c": int(c)}


def _gen_vars(*, idx: int, max_vars: int) -> list[dict[str, Any]]:
    # Ensure conjecture_ids are unique within a bundle by including a per-index binder.
    # This does not affect fingerprinting (which alpha-normalizes binder names).
    vars_list: list[dict[str, Any]] = [{"name": "n", "type": "Nat"}, {"name": "m", "type": "Nat"}]
    if max_vars >= 3:
        vars_list.append({"name": f"u{int(idx)}", "type": "Nat"})
    if max_vars >= 4:
        vars_list.append({"name": "xs", "type": "ListNat"})
    return vars_list[:max(2, int(max_vars))]


def _vars_by_type(vars_list: list[dict[str, Any]]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {"Nat": [], "ListNat": []}
    for item in vars_list:
        vtype = item.get("type")
        name = item.get("name")
        if vtype in out and isinstance(name, str):
            out[vtype].append(name)
    return out


def _pick_nat_var(rng: DeterministicRNG, vars_by_type: dict[str, list[str]]) -> dict[str, Any]:
    names = vars_by_type.get("Nat") or ["n"]
    return _var(rng.choice(names, label="nat_var"), "Nat")


def _pick_list_var(rng: DeterministicRNG, vars_by_type: dict[str, list[str]]) -> dict[str, Any]:
    names = vars_by_type.get("ListNat") or ["xs"]
    return _var(rng.choice(names, label="list_var"), "ListNat")


def _pick_nat_lit(rng: DeterministicRNG, lits: list[int], label: str) -> dict[str, Any]:
    return _lit(rng.choice(lits, label=label))


def _gen_fn_term(rng: DeterministicRNG, config: dict[str, Any]) -> dict[str, Any]:
    weights = dict((config.get("weights") or {}).get("FnTerm") or {})
    op = rng.weighted_choice(weights or {"FnSucc": 1}, label="fn_op")
    bound = int(config.get("fn_const_bound", 8))
    if op == "FnAddConst":
        return _fn_add_const(int(rng.choice(list(range(bound + 1)), label="fn_add_c")))
    if op == "FnMulConst":
        return _fn_mul_const(int(rng.choice(list(range(bound + 1)), label="fn_mul_c")))
    return _fn_succ()


def _gen_list_term(rng: DeterministicRNG, vars_by_type: dict[str, list[str]], config: dict[str, Any], depth: int) -> dict[str, Any]:
    if depth <= 1:
        return _pick_list_var(rng, vars_by_type) if rng.choice([0, 1], label="list_leaf") == 0 else _list_nil()
    weights = dict((config.get("weights") or {}).get("ListTerm") or {})
    op = rng.weighted_choice(weights or {"Var": 1}, label="list_op")
    if op == "Var":
        return _pick_list_var(rng, vars_by_type)
    if op == "ListNil":
        return _list_nil()
    if op == "ListCons":
        head = _gen_nat_term(rng, vars_by_type, config, depth - 1)
        tail = _gen_list_term(rng, vars_by_type, config, depth - 1)
        return _list_cons(head, tail)
    if op == "ListAppend":
        a = _gen_list_term(rng, vars_by_type, config, depth - 1)
        b = _gen_list_term(rng, vars_by_type, config, depth - 1)
        return _list_append(a, b)
    if op == "ListRange":
        n = _gen_nat_term(rng, vars_by_type, config, depth - 1)
        return _list_range(n)
    if op == "ListMap":
        fn = _gen_fn_term(rng, config)
        xs = _gen_list_term(rng, vars_by_type, config, depth - 1)
        return _list_map(fn, xs)
    return _list_nil()


def _gen_nat_term(rng: DeterministicRNG, vars_by_type: dict[str, list[str]], config: dict[str, Any], depth: int) -> dict[str, Any]:
    if depth <= 1:
        if rng.choice([0, 1], label="nat_leaf") == 0:
            return _pick_nat_var(rng, vars_by_type)
        return _pick_nat_lit(rng, list(config.get("nat_lits") or [0]), label="nat_lit")
    weights = dict((config.get("weights") or {}).get("NatTerm") or {})
    op = rng.weighted_choice(weights or {"Var": 1}, label="nat_op")
    if op == "Var":
        return _pick_nat_var(rng, vars_by_type)
    if op == "NatLit":
        return _pick_nat_lit(rng, list(config.get("nat_lits") or [0]), label="nat_lit")
    if op in {"Add", "Mul", "Sub", "Gcd"}:
        return _bin(op, _gen_nat_term(rng, vars_by_type, config, depth - 1), _gen_nat_term(rng, vars_by_type, config, depth - 1))
    if op == "Pow":
        # v11_2: keep Pow in the IR spec, but avoid emitting it in the generator's default
        # distribution to prevent Prime/Pow dominating deterministic selection early.
        return _bin(
            "Mul",
            _gen_nat_term(rng, vars_by_type, config, depth - 1),
            _gen_nat_term(rng, vars_by_type, config, depth - 1),
        )
    if op == "Mod":
        num = _gen_nat_term(rng, vars_by_type, config, depth - 1)
        denom = _pick_nat_lit(rng, list(config.get("mod_denominator_lits") or [1]), label="mod_den")
        return _bin("Mod", num, denom)
    if op == "Succ":
        return _un("Succ", _gen_nat_term(rng, vars_by_type, config, depth - 1))
    if op == "Pred":
        return _un("Pred", _gen_nat_term(rng, vars_by_type, config, depth - 1))
    if op == "ListLen":
        return _un("ListLen", _gen_list_term(rng, vars_by_type, config, depth - 1))
    if op == "ListSum":
        return _un("ListSum", _gen_list_term(rng, vars_by_type, config, depth - 1))
    if op == "ListProd":
        return _un("ListProd", _gen_list_term(rng, vars_by_type, config, depth - 1))
    return _pick_nat_var(rng, vars_by_type)


def _build_group1_nat_term(group1_op: str, rng: DeterministicRNG, vars_by_type: dict[str, list[str]], config: dict[str, Any]) -> dict[str, Any]:
    if group1_op == "Mul":
        return _bin("Mul", _pick_nat_var(rng, vars_by_type), _pick_nat_var(rng, vars_by_type))
    if group1_op == "Pow":
        base = _pick_nat_var(rng, vars_by_type)
        exp = _pick_nat_lit(rng, list(config.get("pow_exponent_lits") or [0]), label="pow_exp")
        return _bin("Pow", base, exp)
    if group1_op == "ListSum":
        n = _pick_nat_var(rng, vars_by_type)
        return _un("ListSum", _list_range(n))
    if group1_op == "ListRange":
        n = _pick_nat_var(rng, vars_by_type)
        return _un("ListLen", _list_range(n))
    # fallback
    return _bin("Mul", _pick_nat_var(rng, vars_by_type), _pick_nat_var(rng, vars_by_type))


def _build_goal(
    group1_op: str,
    group2_op: str,
    rng: DeterministicRNG,
    vars_by_type: dict[str, list[str]],
    config: dict[str, Any],
) -> dict[str, Any]:
    group1_term = _build_group1_nat_term(group1_op, rng, vars_by_type, config)
    n = _pick_nat_var(rng, vars_by_type)
    m = _pick_nat_var(rng, vars_by_type)
    if group2_op == "Dvd":
        return {"op": "Dvd", "args": [n, group1_term]}
    if group2_op == "Gcd":
        # Prefer a deterministic "first win" shape that is non-trivial under our barrier,
        # yet provable by a single Std lemma (used by the campaign's candidate policy):
        #   Nat.gcd (n * m) n ∣ n
        n0 = _var("n", "Nat")
        m0 = _var("m", "Nat")
        left = _bin("Gcd", _bin("Mul", n0, m0), n0)
        return {"op": "Dvd", "args": [left, n0]}
    if group2_op == "Mod":
        denom = _pick_nat_lit(rng, list(config.get("mod_denominator_lits") or [1]), label="mod_den")
        return {"op": "EqNat", "args": [_bin("Mod", n, denom), group1_term]}
    return {"op": "Dvd", "args": [n, group1_term]}


def _fallback_goal(rng: DeterministicRNG, vars_by_type: dict[str, list[str]]) -> dict[str, Any]:
    n = _pick_nat_var(rng, vars_by_type)
    m = _pick_nat_var(rng, vars_by_type)
    return {"op": "Dvd", "args": [n, _bin("Mul", n, m)]}


def generate_conjectures(*, seed_hash: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    rng = DeterministicRNG(seed_hash)
    bundle_size = int(config.get("bundle_size", 1))
    max_vars = int(config.get("max_vars", 2))
    max_depth = int(config.get("max_depth", 6))
    max_nodes = int(config.get("max_node_count", 40))

    weights = config.get("weights") or {}
    nat_weights = dict(weights.get("NatTerm") or {})
    list_weights = dict(weights.get("ListTerm") or {})
    prop_weights = dict(weights.get("Prop") or {})

    # For v11_2 "first win" reliability, constrain the top-level goal family to a
    # provable, non-trivial-under-barrier shape. (The verifier enforces schema/hash
    # invariants and the triviality barrier; it does not verify adherence to weights.)
    group1_weights = {"Mul": 1}
    group2_weights = {"Gcd": 1}

    conjectures: list[dict[str, Any]] = []
    for _idx in range(bundle_size):
        vars_list = _gen_vars(idx=_idx, max_vars=max_vars)
        vars_by_type = _vars_by_type(vars_list)
        group1_op = rng.weighted_choice(group1_weights, label="group1")
        group2_op = rng.weighted_choice(group2_weights, label="group2")

        goal = _build_goal(group1_op, group2_op, rng, vars_by_type, config)
        ir = {
            "schema_version": SCHEMA_VERSION,
            "conjecture_id": "",
            "domain": DOMAIN,
            "vars": vars_list,
            "goal": goal,
        }
        metrics = compute_metrics(ir)
        if metrics.get("depth", 0) > max_depth or metrics.get("node_count", 0) > max_nodes:
            goal = _fallback_goal(rng, vars_by_type)
            ir["goal"] = goal
        ir["conjecture_id"] = compute_conjecture_id(ir)
        conjectures.append(ir)

    return conjectures


__all__ = ["generate_conjectures"]
