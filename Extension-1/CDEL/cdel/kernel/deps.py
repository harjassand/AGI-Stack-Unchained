"""Dependency extraction for symbol references."""

from __future__ import annotations

from typing import Iterable


def collect_sym_refs(term: dict) -> set[str]:
    refs: set[str] = set()

    def visit(node: dict) -> None:
        if not isinstance(node, dict):
            return
        tag = node.get("tag")
        if tag == "sym":
            name = node.get("name")
            if isinstance(name, str):
                refs.add(name)
            return
        if tag == "var":
            return
        if tag in {"int", "bool", "nil", "none"}:
            return
        if tag == "some":
            visit(node.get("value"))
            return
        if tag == "cons":
            visit(node.get("head"))
            visit(node.get("tail"))
            return
        if tag == "if":
            visit(node.get("cond"))
            visit(node.get("then"))
            visit(node.get("else"))
            return
        if tag == "app":
            visit(node.get("fn"))
            args = node.get("args") or []
            if isinstance(args, list):
                for arg in args:
                    visit(arg)
            return
        if tag == "prim":
            args = node.get("args") or []
            if isinstance(args, list):
                for arg in args:
                    visit(arg)
            return
        if tag == "pair":
            visit(node.get("left"))
            visit(node.get("right"))
            return
        if tag in {"fst", "snd"}:
            visit(node.get("pair"))
            return
        if tag == "match_list":
            visit(node.get("scrutinee"))
            visit(node.get("nil_case"))
            cons_case = node.get("cons_case") or {}
            if isinstance(cons_case, dict):
                visit(cons_case.get("body"))
            return
        if tag == "match_option":
            visit(node.get("scrutinee"))
            visit(node.get("none_case"))
            some_case = node.get("some_case") or {}
            if isinstance(some_case, dict):
                visit(some_case.get("body"))
            return
        raise ValueError(f"unknown term tag: {tag}")

    visit(term)
    return refs


def collect_sym_refs_in_defs(defs: Iterable[dict]) -> set[str]:
    refs: set[str] = set()
    for defn in defs:
        body = defn.get("body")
        if body is None:
            continue
        refs.update(collect_sym_refs(body))
    return refs


def collect_sym_refs_in_specs(specs: Iterable[dict]) -> set[str]:
    refs: set[str] = set()
    for spec in specs:
        if spec.get("kind") == "forall":
            domain = spec.get("domain") or {}
            if isinstance(domain, dict):
                fun_symbols = domain.get("fun_symbols") or []
                if isinstance(fun_symbols, list):
                    for name in fun_symbols:
                        if isinstance(name, str):
                            refs.add(name)
            term = spec.get("assert")
            if term is None:
                continue
            refs.update(collect_sym_refs(term))
            continue
        if spec.get("kind") == "stat_cert":
            baseline = spec.get("baseline_symbol")
            candidate = spec.get("candidate_symbol")
            eval_cfg = spec.get("eval") or {}
            oracle = eval_cfg.get("oracle_symbol") if isinstance(eval_cfg, dict) else None
            for name in (baseline, candidate, oracle):
                if isinstance(name, str):
                    refs.add(name)
            continue
        if spec.get("kind") in {"proof", "proof_unbounded"}:
            goal = spec.get("goal") or {}
            refs.update(collect_sym_refs(goal.get("lhs") or {}))
            refs.update(collect_sym_refs(goal.get("rhs") or {}))
            continue
        term = spec.get("assert")
        if term is None:
            continue
        refs.update(collect_sym_refs(term))
    return refs
