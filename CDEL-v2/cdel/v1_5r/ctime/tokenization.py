"""Macro tokenization + rho reporting for v1.5r (RSI-L3 composition-aware).

Supports:
- Leaf macros whose body expands to primitives.
- Composed macros whose body references other macros (CALL_MACRO ops).

Encoding:
- Pass 1: greedy longest-match using leaf macros over primitive action stream.
- Pass 2: greedy longest-match using composed macros over token stream of macro IDs.

This yields:
- delta_tokens_total (overall savings vs primitives)
- per-macro: is_composed + delta_tokens_token_space_est (savings in macro-token space)
"""

from __future__ import annotations

from typing import Any


def _get_action_name(e: dict[str, Any]) -> str | None:
    a = e.get("action_name")
    if isinstance(a, str):
        return a
    act = e.get("action")
    if isinstance(act, dict):
        n = act.get("name")
        if isinstance(n, str):
            return n
    return None


def _is_call_op(op: Any) -> bool:
    return isinstance(op, dict) and (
        (op.get("op") == "CALL_MACRO" and isinstance(op.get("macro_id"), str))
        or (
            op.get("name") == "CALL_MACRO"
            and isinstance(op.get("args"), dict)
            and isinstance(op["args"].get("macro_id"), str)
        )
    )


def _call_macro_id(op: dict[str, Any]) -> str:
    if op.get("op") == "CALL_MACRO":
        return op["macro_id"]
    return op["args"]["macro_id"]


def _is_prim_op(op: Any) -> bool:
    return isinstance(op, dict) and isinstance(op.get("name"), str) and not _is_call_op(op)


def _expand_to_primitives(macro_id: str, macro_map: dict[str, dict[str, Any]], stack: list[str]) -> list[str]:
    if macro_id in stack:
        raise RuntimeError(f"macro cycle detected: {' -> '.join(stack + [macro_id])}")
    m = macro_map.get(macro_id)
    if not m:
        raise RuntimeError(f"missing macro def for {macro_id}")
    body = m.get("body", [])
    if not isinstance(body, list):
        raise RuntimeError(f"invalid macro body for {macro_id}")
    out: list[str] = []
    stack2 = stack + [macro_id]
    for op in body:
        if _is_call_op(op):
            out.extend(_expand_to_primitives(_call_macro_id(op), macro_map, stack2))
        elif _is_prim_op(op):
            out.append(op["name"])
        else:
            raise RuntimeError(f"invalid op in macro {macro_id}: {op}")
    return out


def _leaf_and_composed(macros: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    leaf = []
    comp = []
    for m in macros:
        body = m.get("body", [])
        if not isinstance(body, list):
            continue
        has_call = any(_is_call_op(op) for op in body)
        has_prim = any(_is_prim_op(op) for op in body)
        if has_call and not has_prim:
            comp.append(m)
        else:
            leaf.append(m)
    return leaf, comp


def _greedy_pass_leaf(prims: list[str], leaf_macros: list[dict[str, Any]], macro_map: dict[str, dict[str, Any]]) -> list[tuple[str, str]]:
    patterns: list[tuple[str, list[str]]] = []
    for m in leaf_macros:
        mid = m.get("macro_id")
        if not isinstance(mid, str):
            continue
        exp = _expand_to_primitives(mid, macro_map, [])
        if len(exp) >= 2:
            patterns.append((mid, exp))
    patterns.sort(key=lambda x: (-len(x[1]), x[0]))

    out: list[tuple[str, str]] = []
    i = 0
    n = len(prims)
    while i < n:
        matched = None
        for mid, pat in patterns:
            k = len(pat)
            if i + k <= n and prims[i : i + k] == pat:
                matched = (mid, k)
                break
        if matched:
            mid, k = matched
            out.append(("M", mid))
            i += k
        else:
            out.append(("P", prims[i]))
            i += 1
    return out


def _composed_patterns(comp_macros: list[dict[str, Any]]) -> list[tuple[str, list[str]]]:
    pats: list[tuple[str, list[str]]] = []
    for m in comp_macros:
        mid = m.get("macro_id")
        if not isinstance(mid, str):
            continue
        body = m.get("body", [])
        if not isinstance(body, list) or len(body) < 2:
            continue
        call_ids: list[str] = []
        ok = True
        for op in body:
            if not isinstance(op, dict) or not _is_call_op(op):
                ok = False
                break
            call_ids.append(_call_macro_id(op))
        if ok:
            pats.append((mid, call_ids))
    pats.sort(key=lambda x: (-len(x[1]), x[0]))
    return pats


def _greedy_pass_comp(tokens: list[tuple[str, str]], comp_macros: list[dict[str, Any]]) -> list[tuple[str, str]]:
    pats = _composed_patterns(comp_macros)
    out: list[tuple[str, str]] = []
    i = 0
    n = len(tokens)
    while i < n:
        matched = None
        for mid, pat in pats:
            k = len(pat)
            if i + k <= n:
                window = tokens[i : i + k]
                if all(t[0] == "M" for t in window) and [t[1] for t in window] == pat:
                    matched = (mid, k)
                    break
        if matched:
            mid, k = matched
            out.append(("M", mid))
            i += k
        else:
            out.append(tokens[i])
            i += 1
    return out


def build_macro_tokenization_report(
    *,
    epoch_id: str,
    trace_events: list[dict[str, Any]],
    macro_defs: list[dict[str, Any]],
    macro_active_set_hash: str,
    trace_corpus_hashes: list[str],
) -> dict[str, Any]:
    prims: list[str] = []
    for e in trace_events:
        if not isinstance(e, dict):
            continue
        an = _get_action_name(e)
        if isinstance(an, str):
            prims.append(an)

    macro_map: dict[str, dict[str, Any]] = {}
    for m in macro_defs:
        mid = m.get("macro_id")
        if isinstance(mid, str):
            macro_map[mid] = m

    leaf, comp = _leaf_and_composed(macro_defs)

    t1 = _greedy_pass_leaf(prims, leaf, macro_map)
    t2 = _greedy_pass_comp(t1, comp)

    primitive_tokens_total = len(prims)
    token_tokens_total = len(t2)
    delta_tokens_total = max(0, primitive_tokens_total - token_tokens_total)

    occ: dict[str, int] = {}
    for kind, val in t2:
        if kind == "M":
            occ[val] = occ.get(val, 0) + 1

    macros_out: list[dict[str, Any]] = []
    for mid, count in sorted(occ.items()):
        m = macro_map.get(mid) or {}
        body = m.get("body", [])
        is_comp = isinstance(body, list) and all(isinstance(op, dict) and _is_call_op(op) for op in body)
        token_savings = (len(body) - 1) * count if is_comp else 0

        try:
            exp_len = len(_expand_to_primitives(mid, macro_map, []))
        except Exception:
            exp_len = 0

        macros_out.append(
            {
                "macro_id": mid,
                "occurrences": int(count),
                "expanded_primitive_len": int(exp_len),
                "delta_tokens_token_space_est": int(token_savings),
                "is_composed": bool(is_comp),
            }
        )

    return {
        "schema": "macro_tokenization_report_v1",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "macro_active_set_hash": macro_active_set_hash,
        "trace_corpus_hashes": trace_corpus_hashes,
        "primitive_tokens_total": primitive_tokens_total,
        "token_tokens_total": token_tokens_total,
        "delta_tokens_total": delta_tokens_total,
        "macros": macros_out,
    }


def build_rho_report(*, epoch_id: str, tokenization_report: dict[str, Any]) -> dict[str, Any]:
    rho_num = int(tokenization_report.get("delta_tokens_total", 0))
    rho_den = int(tokenization_report.get("primitive_tokens_total", 1))
    if rho_den <= 0:
        rho_den = 1
    return {
        "schema": "rho_report_v1",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "encoder_rule_id": "greedy-longest-match-v1",
        "macro_active_set_hash": tokenization_report.get("macro_active_set_hash"),
        "trace_corpus_hashes": tokenization_report.get("trace_corpus_hashes", []),
        "rho_num": rho_num,
        "rho_den": rho_den,
    }
