"""Canonicalization and hashing for module payloads."""

from __future__ import annotations

import json
from typing import Any, Iterable

from blake3 import blake3

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
from cdel.kernel.parse import parse_term
from cdel.kernel.types import type_from_json, type_to_json


CANON_JSON_KW = {
    "sort_keys": True,
    "separators": (",", ":"),
    "ensure_ascii": True,
}


def canonical_json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, **CANON_JSON_KW).encode("utf-8")


def payload_hash_hex(payload: dict) -> str:
    data = canonical_json_bytes(payload)
    return blake3(data).hexdigest()


def _parse_term(node: dict, env: list[str]) -> Term:
    return parse_term(node, env)


def _term_to_canon_json(term: Term, env: list[str]) -> dict:
    if isinstance(term, Var):
        if term.idx >= len(env):
            raise ValueError("var index out of range")
        return {"tag": "var", "name": env[term.idx]}
    if isinstance(term, Sym):
        return {"tag": "sym", "name": term.name}
    if isinstance(term, IntLit):
        return {"tag": "int", "value": term.value}
    if isinstance(term, BoolLit):
        return {"tag": "bool", "value": term.value}
    if isinstance(term, Nil):
        return {"tag": "nil"}
    if isinstance(term, OptionNone):
        return {"tag": "none"}
    if isinstance(term, OptionSome):
        return {"tag": "some", "value": _term_to_canon_json(term.value, env)}
    if isinstance(term, Cons):
        return {
            "tag": "cons",
            "head": _term_to_canon_json(term.head, env),
            "tail": _term_to_canon_json(term.tail, env),
        }
    if isinstance(term, Pair):
        return {
            "tag": "pair",
            "left": _term_to_canon_json(term.left, env),
            "right": _term_to_canon_json(term.right, env),
        }
    if isinstance(term, Fst):
        return {"tag": "fst", "pair": _term_to_canon_json(term.pair, env)}
    if isinstance(term, Snd):
        return {"tag": "snd", "pair": _term_to_canon_json(term.pair, env)}
    if isinstance(term, If):
        return {
            "tag": "if",
            "cond": _term_to_canon_json(term.cond, env),
            "then": _term_to_canon_json(term.then, env),
            "else": _term_to_canon_json(term.els, env),
        }
    if isinstance(term, App):
        return {
            "tag": "app",
            "fn": _term_to_canon_json(term.fn, env),
            "args": [_term_to_canon_json(arg, env) for arg in term.args],
        }
    if isinstance(term, Prim):
        return {
            "tag": "prim",
            "op": term.op,
            "args": [_term_to_canon_json(arg, env) for arg in term.args],
        }
    if isinstance(term, MatchList):
        depth = len(env)
        head_name = f"h{depth}"
        tail_name = f"t{depth}"
        env2 = [tail_name, head_name] + env
        return {
            "tag": "match_list",
            "scrutinee": _term_to_canon_json(term.scrutinee, env),
            "nil_case": _term_to_canon_json(term.nil_case, env),
            "cons_case": {
                "head_var": head_name,
                "tail_var": tail_name,
                "body": _term_to_canon_json(term.cons_body, env2),
            },
        }
    if isinstance(term, MatchOption):
        depth = len(env)
        some_name = f"o{depth}"
        env2 = [some_name] + env
        return {
            "tag": "match_option",
            "scrutinee": _term_to_canon_json(term.scrutinee, env),
            "none_case": _term_to_canon_json(term.none_case, env),
            "some_case": {
                "var": some_name,
                "body": _term_to_canon_json(term.some_body, env2),
            },
        }
    raise ValueError(f"unknown term type: {term}")


def _canon_params(params: list[dict]) -> tuple[list[dict], list[str], list[str]]:
    canonical_names = [f"p{i}" for i in range(len(params))]
    original_names = [p.get("name") for p in params]
    if any(name is None for name in original_names):
        raise ValueError("param name missing")
    if len(set(original_names)) != len(original_names):
        raise ValueError("duplicate param name")
    canon_params = []
    for name, param in zip(canonical_names, params):
        typ = type_from_json(param.get("type"))
        canon_params.append({"name": name, "type": type_to_json(typ)})
    return canon_params, original_names, canonical_names


def _canon_vars(vars_list: list[dict], prefix: str) -> tuple[list[dict], list[str], list[str]]:
    canonical_names = [f"{prefix}{i}" for i in range(len(vars_list))]
    original_names = [v.get("name") for v in vars_list]
    if any(name is None for name in original_names):
        raise ValueError("var name missing")
    if len(set(original_names)) != len(original_names):
        raise ValueError("duplicate var name")
    canon_vars = []
    for name, var in zip(canonical_names, vars_list):
        typ = type_from_json(var.get("type"))
        canon_vars.append({"name": name, "type": type_to_json(typ)})
    return canon_vars, original_names, canonical_names


def _rename_term(term_node: dict, original_env: list[str], canon_env: list[str]) -> dict:
    internal = _parse_term(term_node, original_env)
    return _term_to_canon_json(internal, canon_env)


def canonicalize_definition(defn: dict) -> dict:
    params = defn.get("params") or []
    if not isinstance(params, list):
        raise ValueError("params must be a list")
    canon_params, orig_names, canon_names = _canon_params(params)
    env_orig = list(reversed(orig_names))
    env_canon = list(reversed(canon_names))
    body = _rename_term(defn.get("body"), env_orig, env_canon)
    ret_type = type_to_json(type_from_json(defn.get("ret_type")))
    termination = defn.get("termination") or {}
    decreases_param = termination.get("decreases_param")
    if decreases_param is not None:
        if decreases_param not in orig_names:
            raise ValueError("termination decreases_param not in params")
        dec_index = orig_names.index(decreases_param)
        decreases_param = canon_names[dec_index]
    canon_term = {
        "kind": termination.get("kind"),
        "decreases_param": decreases_param,
    }
    return {
        "name": defn.get("name"),
        "params": canon_params,
        "ret_type": ret_type,
        "body": body,
        "termination": canon_term,
    }


def canonicalize_spec(spec: dict) -> dict:
    kind = spec.get("kind")
    if kind == "stat_cert":
        return _canonicalize_stat_cert(spec)
    if kind in {"proof", "proof_unbounded"}:
        goal = spec.get("goal") or {}
        canon_goal = {
            "tag": "eq",
            "lhs": _rename_term(goal.get("lhs"), [], []),
            "rhs": _rename_term(goal.get("rhs"), [], []),
        }
        canon_proof = _canonicalize_proof(spec.get("proof"))
        return {
            "kind": kind,
            "goal": canon_goal,
            "proof": canon_proof,
        }

    vars_list = spec.get("vars") or []
    if not isinstance(vars_list, list):
        raise ValueError("spec vars must be a list")
    canon_vars, orig_names, canon_names = _canon_vars(vars_list, "v")
    env_orig = list(reversed(orig_names))
    env_canon = list(reversed(canon_names))
    assert_term = _rename_term(spec.get("assert"), env_orig, env_canon)
    domain = spec.get("domain") or {}
    fun_symbols = domain.get("fun_symbols") or []
    if not isinstance(fun_symbols, list):
        raise ValueError("fun_symbols must be a list")
    if any(not isinstance(name, str) for name in fun_symbols):
        raise ValueError("fun_symbols must be strings")
    def require_int(label: str) -> int:
        value = domain.get(label)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{label} must be an int")
        return value

    canon_domain = {
        "int_min": require_int("int_min"),
        "int_max": require_int("int_max"),
        "list_max_len": require_int("list_max_len"),
        "fun_symbols": sorted(fun_symbols),
    }
    return {
        "kind": kind,
        "vars": canon_vars,
        "domain": canon_domain,
        "assert": assert_term,
    }


def _canonicalize_stat_cert(spec: dict) -> dict:
    def require_str(label: str) -> str:
        value = spec.get(label)
        if not isinstance(value, str):
            raise ValueError(f"{label} must be a string")
        return value

    def require_int(label: str, source: dict) -> int:
        value = source.get(label)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{label} must be an int")
        return value

    def require_decimal_str(label: str, source: dict) -> str:
        value = source.get(label)
        if not isinstance(value, str):
            raise ValueError(f"{label} must be a string")
        if not value:
            raise ValueError(f"{label} must be a non-empty string")
        return value

    def require_evalue(source: dict) -> dict:
        value = source.get("evalue")
        if not isinstance(value, dict):
            raise ValueError("evalue must be an object")
        mantissa = value.get("mantissa")
        exponent10 = value.get("exponent10")
        if not isinstance(mantissa, str) or not mantissa:
            raise ValueError("evalue mantissa must be a string")
        if isinstance(exponent10, bool) or not isinstance(exponent10, int):
            raise ValueError("evalue exponent10 must be an int")
        return {"mantissa": mantissa, "exponent10": exponent10}

    eval_cfg = spec.get("eval") or {}
    if not isinstance(eval_cfg, dict):
        raise ValueError("eval must be an object")
    risk = spec.get("risk") or {}
    if not isinstance(risk, dict):
        raise ValueError("risk must be an object")
    certificate = spec.get("certificate") or {}
    if not isinstance(certificate, dict):
        raise ValueError("certificate must be an object")

    paired = eval_cfg.get("paired_seeds")
    if not isinstance(paired, bool):
        raise ValueError("paired_seeds must be a bool")

    oracle_symbol = eval_cfg.get("oracle_symbol")
    if not isinstance(oracle_symbol, str):
        raise ValueError("oracle_symbol must be a string")

    canon_eval = {
        "episodes": require_int("episodes", eval_cfg),
        "max_steps": require_int("max_steps", eval_cfg),
        "paired_seeds": paired,
        "oracle_symbol": oracle_symbol,
        "eval_harness_id": require_str_from(eval_cfg, "eval_harness_id"),
        "eval_harness_hash": require_str_from(eval_cfg, "eval_harness_hash"),
        "eval_suite_hash": require_str_from(eval_cfg, "eval_suite_hash"),
    }
    canon_risk = {
        "alpha_i": require_decimal_str("alpha_i", risk),
        "evalue_threshold": require_decimal_str("evalue_threshold", risk),
        "alpha_schedule": _canonicalize_alpha_schedule(risk.get("alpha_schedule")),
    }
    canon_certificate = {
        "n": require_int("n", certificate),
        "baseline_successes": require_int("baseline_successes", certificate),
        "candidate_successes": require_int("candidate_successes", certificate),
        "diff_sum": require_int("diff_sum", certificate),
        "diff_min": require_int("diff_min", certificate),
        "diff_max": require_int("diff_max", certificate),
        "evalue": require_evalue(certificate),
        "transcript_hash": require_str_from(certificate, "transcript_hash"),
        "signature": require_str_from(certificate, "signature"),
        "signature_scheme": require_str_from(certificate, "signature_scheme"),
        "key_id": require_str_from(certificate, "key_id"),
    }
    if "evalue_schema_version" in certificate:
        canon_certificate["evalue_schema_version"] = certificate.get("evalue_schema_version")
    return {
        "kind": "stat_cert",
        "concept": require_str("concept"),
        "metric": require_str("metric"),
        "null": require_str("null"),
        "baseline_symbol": require_str("baseline_symbol"),
        "candidate_symbol": require_str("candidate_symbol"),
        "eval": canon_eval,
        "risk": canon_risk,
        "certificate": canon_certificate,
    }


def require_str_from(source: dict, label: str) -> str:
    value = source.get(label)
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    return value


def _canonicalize_alpha_schedule(raw: object) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("alpha_schedule must be an object")
    name = raw.get("name")
    if not isinstance(name, str):
        raise ValueError("alpha_schedule name must be a string")
    exponent = raw.get("exponent")
    if isinstance(exponent, bool) or not isinstance(exponent, int) or exponent <= 1:
        raise ValueError("alpha_schedule exponent must be an int > 1")
    coefficient = raw.get("coefficient")
    if not isinstance(coefficient, str):
        raise ValueError("alpha_schedule coefficient must be a string")
    return {"name": name, "exponent": exponent, "coefficient": coefficient}


def _canonicalize_proof(node: dict) -> dict:
    if not isinstance(node, dict):
        raise ValueError("proof must be an object")
    tag = node.get("tag")
    if tag == "missing":
        return {"tag": "missing"}
    if tag == "by_eval":
        return {"tag": "by_eval"}
    if tag == "refl":
        return {"tag": "refl", "term": _rename_term(node.get("term"), [], [])}
    if tag == "sym":
        return {"tag": "sym", "proof": _canonicalize_proof(node.get("proof"))}
    if tag == "trans":
        return {
            "tag": "trans",
            "left": _canonicalize_proof(node.get("left")),
            "right": _canonicalize_proof(node.get("right")),
        }
    raise ValueError(f"unknown proof tag: {tag}")


def canonicalize_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    new_symbols = payload.get("new_symbols") or []
    declared_deps = payload.get("declared_deps") or []
    definitions = payload.get("definitions") or []
    specs = payload.get("specs") or []
    concepts = payload.get("concepts")
    if not isinstance(new_symbols, list):
        raise ValueError("new_symbols must be a list")
    if not isinstance(declared_deps, list):
        raise ValueError("declared_deps must be a list")
    if not isinstance(definitions, list):
        raise ValueError("definitions must be a list")
    if not isinstance(specs, list):
        raise ValueError("specs must be a list")
    canon_concepts = None
    if concepts is not None:
        if not isinstance(concepts, list):
            raise ValueError("concepts must be a list")
        canon_concepts = [_canonicalize_concept(c) for c in concepts]
        canon_concepts.sort(key=lambda c: (c["concept"], c["symbol"]))

    canon_defs = [canonicalize_definition(d) for d in definitions]
    canon_defs.sort(key=lambda d: d.get("name"))

    canon_specs = [canonicalize_spec(s) for s in specs]
    canon_specs.sort(key=lambda s: canonical_json_bytes(s))

    canon_payload = {
        "new_symbols": sorted(new_symbols),
        "definitions": canon_defs,
        "declared_deps": sorted(declared_deps),
        "specs": canon_specs,
    }
    if canon_concepts is not None:
        canon_payload["concepts"] = canon_concepts
    if "capacity_claim" in payload:
        claim = payload.get("capacity_claim") or {}
        def require_int(label: str) -> int:
            value = claim.get(label)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{label} must be an int")
            return value
        canon_payload["capacity_claim"] = {
            "ast_nodes": require_int("ast_nodes"),
            "spec_work": require_int("spec_work"),
            "index_impact": require_int("index_impact"),
        }
    return canon_payload


def _canonicalize_concept(entry: dict) -> dict:
    if not isinstance(entry, dict):
        raise ValueError("concept entry must be an object")
    concept = entry.get("concept")
    symbol = entry.get("symbol")
    if not isinstance(concept, str):
        raise ValueError("concept must be a string")
    if not isinstance(symbol, str):
        raise ValueError("concept symbol must be a string")
    return {"concept": concept, "symbol": symbol}


def payload_bytes_and_hash(payload: dict) -> tuple[bytes, str]:
    canon = canonicalize_payload(payload)
    data = canonical_json_bytes(canon)
    return data, blake3(data).hexdigest()


def definition_hash(defn: dict) -> str:
    canon_def = canonicalize_definition(defn)
    data = canonical_json_bytes(canon_def)
    return blake3(data).hexdigest()
