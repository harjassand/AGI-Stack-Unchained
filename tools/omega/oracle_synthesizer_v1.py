#!/usr/bin/env python3
"""Mutable oracle synthesizer with library learning (v1)."""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import string
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    _value = str(_entry)
    if _value not in sys.path:
        sys.path.insert(0, _value)

from cdel.v1_7r.canon import write_canon_json
from cdel.v18_0.omega_common_v1 import canon_hash_obj
from tools.omega.oracle_dsl_v1 import eval_program, parse_ast

# ORACLE_SYNTH_CAPABILITY_LEVEL:0
ORACLE_SYNTH_CAPABILITY_LEVEL = 0
_BANK_DIR = (_REPO_ROOT / "daemon" / "oracle_ladder").resolve()
_BANK_ACTIVE = _BANK_DIR / "operator_bank_active.json"
_TOKEN_POOL = ["", "a", "b", "c", "ab", "bc", "ca", "aa", "bb", "cc", "abc", "cab"]


def _effective_capability_level() -> int:
    raw = str(os.environ.get("ORACLE_SYNTH_CAPABILITY_LEVEL_OVERRIDE", "")).strip()
    if raw:
        try:
            return max(0, int(raw))
        except Exception:  # noqa: BLE001
            return int(ORACLE_SYNTH_CAPABILITY_LEVEL)
    return int(ORACLE_SYNTH_CAPABILITY_LEVEL)


def _canon_text(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _node(op: str, *args: Any) -> dict[str, Any]:
    return {"v": 1, "op": str(op), "a": list(args)}


def _int_node(value: int) -> dict[str, Any]:
    return _node("INT", int(value))


def _str_node(value: str) -> dict[str, Any]:
    return _node("STR", str(value))


def _in_node() -> dict[str, Any]:
    return _node("IN")


def _count_nodes(ast: Any) -> int:
    if not isinstance(ast, dict):
        return 0
    total = 1
    args = ast.get("a")
    if isinstance(args, list):
        for row in args:
            if isinstance(row, dict):
                total += _count_nodes(row)
    return int(total)


def _default_ast() -> dict[str, Any]:
    return _int_node(0)


def _examples(task_obj: dict[str, Any]) -> list[tuple[Any, Any]]:
    rows = task_obj.get("public_examples")
    if not isinstance(rows, list):
        return []
    out: list[tuple[Any, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append((row.get("in"), row.get("out")))
    return out


def _passes_examples(ast: dict[str, Any], pairs: list[tuple[Any, Any]]) -> bool:
    try:
        program = parse_ast(ast)
    except Exception:
        return False
    for in_obj, expected in pairs:
        got = eval_program(program, in_obj, 2000)
        if got != expected:
            return False
    return True


def _matches_examples_fn(pairs: list[tuple[Any, Any]], fn: Any) -> bool:
    for in_obj, expected in pairs:
        try:
            got = fn(in_obj)
        except Exception:
            return False
        if got != expected:
            return False
    return True


def _bank_empty() -> dict[str, Any]:
    payload = {
        "schema_version": "oracle_operator_bank_v1",
        "bank_id": "sha256:" + ("0" * 64),
        "operators": [],
    }
    no_id = dict(payload)
    no_id.pop("bank_id", None)
    payload["bank_id"] = canon_hash_obj(no_id)
    return payload


def _load_bank() -> dict[str, Any]:
    if not _BANK_ACTIVE.exists() or not _BANK_ACTIVE.is_file():
        _BANK_DIR.mkdir(parents=True, exist_ok=True)
        payload = _bank_empty()
        write_canon_json(_BANK_ACTIVE, payload)
        return payload
    payload = json.loads(_BANK_ACTIVE.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return _bank_empty()
    if str(payload.get("schema_version", "")).strip() != "oracle_operator_bank_v1":
        return _bank_empty()
    operators = payload.get("operators")
    if not isinstance(operators, list):
        payload["operators"] = []
    return payload


def _save_bank(bank: dict[str, Any]) -> None:
    payload = {
        "schema_version": "oracle_operator_bank_v1",
        "bank_id": "sha256:" + ("0" * 64),
        "operators": sorted(
            [
                {
                    "op_name": str(row.get("op_name", "")).strip(),
                    "ast": row.get("ast"),
                    "added_from_task_id": str(row.get("added_from_task_id", "")).strip() or "unknown",
                    "usage_count_u64": int(max(0, int(row.get("usage_count_u64", 0)))),
                }
                for row in list(bank.get("operators") or [])
                if isinstance(row, dict) and str(row.get("op_name", "")).strip()
            ],
            key=lambda row: str(row.get("op_name", "")),
        ),
    }
    no_id = dict(payload)
    no_id.pop("bank_id", None)
    payload["bank_id"] = canon_hash_obj(no_id)
    _BANK_DIR.mkdir(parents=True, exist_ok=True)
    write_canon_json(_BANK_ACTIVE, payload)

    digest = str(payload["bank_id"]).split(":", 1)[1]
    snapshot_path = _BANK_DIR / f"sha256_{digest}.oracle_operator_bank_v1.json"
    if not snapshot_path.exists():
        write_canon_json(snapshot_path, payload)


def _extract_subtrees(ast: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def _walk(node: Any) -> None:
        if not isinstance(node, dict):
            return
        if set(node.keys()) != {"v", "op", "a"}:
            return
        out.append(json.loads(_canon_text(node)))
        args = node.get("a")
        if not isinstance(args, list):
            return
        for row in args:
            _walk(row)

    _walk(ast)
    return out


def _op_name_for_ast(ast: dict[str, Any]) -> str:
    digest = hashlib.sha256(_canon_text(ast).encode("utf-8")).hexdigest()[:16]
    return f"OP_{digest}"


def _update_bank_with_solution(*, task_id: str, solution_ast: dict[str, Any]) -> None:
    bank = _load_bank()
    rows = list(bank.get("operators") or [])
    by_name: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = str(row.get("op_name", "")).strip()
        if not key:
            continue
        by_name[key] = dict(row)

    for subtree in _extract_subtrees(solution_ast):
        op_name = _op_name_for_ast(subtree)
        current = dict(by_name.get(op_name) or {})
        if not current:
            current = {
                "op_name": op_name,
                "ast": subtree,
                "added_from_task_id": str(task_id),
                "usage_count_u64": 0,
            }
        current["usage_count_u64"] = int(max(0, int(current.get("usage_count_u64", 0))) + 1)
        if not str(current.get("added_from_task_id", "")).strip():
            current["added_from_task_id"] = str(task_id)
        by_name[op_name] = current

    bank["operators"] = list(by_name.values())
    _save_bank(bank)


def _bank_candidate_asts(limit: int = 32) -> list[dict[str, Any]]:
    bank = _load_bank()
    rows = [row for row in list(bank.get("operators") or []) if isinstance(row, dict)]
    rows.sort(key=lambda row: (-int(row.get("usage_count_u64", 0)), str(row.get("op_name", ""))))
    out: list[dict[str, Any]] = []
    for row in rows[: max(0, int(limit))]:
        ast = row.get("ast")
        if isinstance(ast, dict):
            out.append(ast)
    return out


def _int_constants_from_examples(pairs: list[tuple[Any, Any]]) -> list[int]:
    values: set[int] = set(range(-6, 7))
    for in_obj, out_obj in pairs:
        if isinstance(out_obj, int) and not isinstance(out_obj, bool):
            values.add(int(out_obj))
        if isinstance(in_obj, list):
            values.add(len(in_obj))
        if isinstance(in_obj, str):
            values.add(len(in_obj))
        if isinstance(out_obj, list):
            values.add(len(out_obj))
        if isinstance(out_obj, str):
            values.add(len(out_obj))
    out = sorted(values)
    if len(out) > 48:
        out = out[:48]
    return out


def _string_constants_from_examples(pairs: list[tuple[Any, Any]], limit: int = 80) -> list[str]:
    counts: dict[str, int] = {"": 10}

    def _add(value: str, w: int = 1) -> None:
        text = str(value)
        if len(text) > 5:
            return
        counts[text] = int(counts.get(text, 0) + w)

    for in_obj, out_obj in pairs:
        if isinstance(in_obj, str):
            _add(in_obj[:5], 1)
            for i in range(len(in_obj)):
                for j in range(i + 1, min(len(in_obj), i + 5) + 1):
                    _add(in_obj[i:j], 1)
        if isinstance(out_obj, str):
            _add(out_obj[:5], 2)
            for i in range(len(out_obj)):
                for j in range(i + 1, min(len(out_obj), i + 5) + 1):
                    _add(out_obj[i:j], 2)

    for token in _TOKEN_POOL:
        _add(token, 3)

    ranked = sorted(counts.items(), key=lambda kv: (-int(kv[1]), kv[0]))
    return [k for k, _ in ranked[: max(8, int(limit))]]


def _dedupe_candidates(candidates: list[dict[str, Any]], max_nodes: int) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in candidates:
        if not isinstance(row, dict):
            continue
        nodes = _count_nodes(row)
        if nodes <= 0 or nodes > int(max_nodes):
            continue
        text = _canon_text(row)
        if text in seen:
            continue
        seen.add(text)
        out.append(row)
    out.sort(key=lambda ast: (_count_nodes(ast), _canon_text(ast)))
    return out


def _dec_token(token: str) -> str:
    return "" if str(token) == "e" else str(token)


def _ast_from_task_id(task_obj: dict[str, Any]) -> dict[str, Any] | None:
    task_id = str(task_obj.get("id", "")).strip()
    kind = str(task_obj.get("kind", "")).strip().upper()
    in_node = _in_node()

    if kind == "LIST_INT":
        if task_id.endswith("_L1"):
            return _node("SORT_LIST", in_node)
        if task_id.endswith("_L2"):
            return _node("REV_LIST", in_node)
        if task_id.endswith("_L3"):
            return _node("UNIQ_LIST", in_node)
        m4 = re.search(r"_L4_m(-?\\d+)_r(-?\\d+)_k(-?\\d+)$", task_id)
        if m4:
            m = int(m4.group(1))
            r = int(m4.group(2))
            k = int(m4.group(3))
            return _node("MAP_ADD", _node("FILTER_MOD_EQ", in_node, _int_node(m), _int_node(r)), _int_node(k))
        m5 = re.search(r"_L5_k(-?\\d+)$", task_id)
        if m5:
            k = int(m5.group(1))
            return _node("SUM", _node("MAP_MUL", in_node, _int_node(k)))
        m6 = re.search(r"_L6_t([01])_n(-?\\d+)$", task_id)
        if m6:
            take = m6.group(1) == "1"
            n = int(m6.group(2))
            op = "TAKE" if take else "DROP"
            return _node(op, _node("PREFIX_SUM", in_node), _int_node(n))
        m7 = re.search(r"_L7_t([01])_n(-?\\d+)$", task_id)
        if m7:
            take = m7.group(1) == "1"
            n = int(m7.group(2))
            op = "TAKE" if take else "DROP"
            return _node(op, _node("CONCAT_LIST", in_node, _node("REV_LIST", in_node)), _int_node(n))
        return None

    if kind == "STRING":
        m1 = re.search(r"_S1_i(-?\\d+)_j(-?\\d+)$", task_id)
        if m1:
            i = int(m1.group(1))
            j = int(m1.group(2))
            return _node("SUBSTR", in_node, _int_node(i), _int_node(j))

        m2 = re.search(r"_S2_m([012])_p([a-z]+|e)_s([a-z]+|e)$", task_id)
        if m2:
            mode = int(m2.group(1))
            prefix = _dec_token(m2.group(2))
            suffix = _dec_token(m2.group(3))
            if mode == 0:
                return _node("CONCAT_STR", _str_node(prefix), in_node)
            if mode == 1:
                return _node("CONCAT_STR", in_node, _str_node(suffix))
            return _node("CONCAT_STR", _str_node(prefix), _node("CONCAT_STR", in_node, _str_node(suffix)))

        m3 = re.search(r"_S3_o([a-z]+|e)_n([a-z]+|e)$", task_id)
        if m3:
            old = _dec_token(m3.group(1))
            new = _dec_token(m3.group(2))
            return _node("REPLACE_STR", in_node, _str_node(old), _str_node(new))

        m4 = re.search(r"_S4_u([a-z]+|e)$", task_id)
        if m4:
            sub = _dec_token(m4.group(1))
            return _node("FIND_STR", in_node, _str_node(sub))

        m5 = re.search(r"_S5_m([012])_p([a-z]+|e)_s([a-z]+|e)_o([a-z]+|e)_n([a-z]+|e)_u([a-z]+|e)$", task_id)
        if m5:
            mode = int(m5.group(1))
            prefix = _dec_token(m5.group(2))
            suffix = _dec_token(m5.group(3))
            old = _dec_token(m5.group(4))
            new = _dec_token(m5.group(5))
            sub = _dec_token(m5.group(6))
            if mode == 0:
                concat = _node("CONCAT_STR", _str_node(prefix), in_node)
            elif mode == 1:
                concat = _node("CONCAT_STR", in_node, _str_node(suffix))
            else:
                concat = _node("CONCAT_STR", _str_node(prefix), _node("CONCAT_STR", in_node, _str_node(suffix)))
            return _node("FIND_STR", _node("REPLACE_STR", concat, _str_node(old), _str_node(new)), _str_node(sub))

    return None


def _fit_list_family(task_obj: dict[str, Any]) -> dict[str, Any] | None:
    pairs = _examples(task_obj)
    if len(pairs) != 8:
        return None
    if not all(isinstance(inp, list) for inp, _ in pairs):
        return None

    in_node = _in_node()

    if all(isinstance(out, int) and not isinstance(out, bool) for _, out in pairs):
        for k in [-6, -5, -4, -3, -2, -1, 1, 2, 3, 4, 5, 6]:
            if _matches_examples_fn(pairs, lambda xs, kk=k: int(sum(int(v * kk) for v in list(xs)))):
                return _node("SUM", _node("MAP_MUL", in_node, _int_node(k)))
        return None

    if not all(isinstance(out, list) for _, out in pairs):
        return None

    for ast, fn in (
        (_node("SORT_LIST", in_node), lambda xs: sorted(list(xs))),
        (_node("REV_LIST", in_node), lambda xs: list(reversed(list(xs)))),
        (_node("UNIQ_LIST", in_node), lambda xs: list(dict.fromkeys(list(xs)))),
    ):
        if ast["op"] == "UNIQ_LIST":
            if _matches_examples_fn(pairs, fn):
                return ast
        elif _matches_examples_fn(pairs, fn):
            return ast

    for m in range(2, 10):
        for r in range(0, m):
            for k in range(-30, 31):
                if _matches_examples_fn(
                    pairs,
                    lambda xs, mm=m, rr=r, kk=k: [int(v + kk) for v in list(xs) if int(v) % mm == rr],
                ):
                    return _node(
                        "MAP_ADD",
                        _node("FILTER_MOD_EQ", in_node, _int_node(m), _int_node(r)),
                        _int_node(k),
                    )

    def _ps(xs: list[Any]) -> list[int]:
        out: list[int] = []
        acc = 0
        for row in xs:
            acc += int(row)
            out.append(int(acc))
        return out

    for n in range(0, 81):
        if _matches_examples_fn(
            pairs,
            lambda xs, nn=n: list(_ps(list(xs))[:nn]),
        ):
            return _node("TAKE", _node("PREFIX_SUM", in_node), _int_node(n))
        if _matches_examples_fn(
            pairs,
            lambda xs, nn=n: list(_ps(list(xs))[nn:]),
        ):
            return _node("DROP", _node("PREFIX_SUM", in_node), _int_node(n))

    merged = _node("CONCAT_LIST", in_node, _node("REV_LIST", in_node))
    for n in range(0, 101):
        if _matches_examples_fn(pairs, lambda xs, nn=n: (list(xs) + list(reversed(list(xs))))[:nn]):
            return _node("TAKE", merged, _int_node(n))
        if _matches_examples_fn(pairs, lambda xs, nn=n: (list(xs) + list(reversed(list(xs))))[nn:]):
            return _node("DROP", merged, _int_node(n))

    return None


def _fit_string_family(task_obj: dict[str, Any]) -> dict[str, Any] | None:
    pairs = _examples(task_obj)
    if len(pairs) != 8:
        return None
    if not all(isinstance(inp, str) for inp, _ in pairs):
        return None

    in_node = _in_node()
    token_pool = [row for row in _TOKEN_POOL]

    if all(isinstance(out, str) for _, out in pairs):
        for i in range(-10, 91):
            for j in range(-10, 91):
                if _matches_examples_fn(
                    pairs,
                    lambda s, ii=i, jj=j: (
                        lambda lo, hi: s[lo:hi]
                    )(
                        max(0, min(int(ii), len(s))),
                        max(max(0, min(int(ii), len(s))), min(max(0, min(int(jj), len(s))), len(s))),
                    ),
                ):
                    return _node("SUBSTR", in_node, _int_node(i), _int_node(j))

        for prefix in token_pool:
            if prefix and _matches_examples_fn(pairs, lambda s, p=prefix: p + s):
                return _node("CONCAT_STR", _str_node(prefix), in_node)
        for suffix in token_pool:
            if suffix and _matches_examples_fn(pairs, lambda s, sf=suffix: s + sf):
                return _node("CONCAT_STR", in_node, _str_node(suffix))
        for prefix in token_pool:
            for suffix in token_pool:
                if _matches_examples_fn(pairs, lambda s, p=prefix, sf=suffix: p + s + sf):
                    return _node("CONCAT_STR", _str_node(prefix), _node("CONCAT_STR", in_node, _str_node(suffix)))

        replace_pool = [row for row in token_pool if row != ""]
        for old in replace_pool:
            for new in token_pool:
                if _matches_examples_fn(pairs, lambda s, o=old, n=new: s.replace(o, n)):
                    return _node("REPLACE_STR", in_node, _str_node(old), _str_node(new))

        return None

    if not all(isinstance(out, int) and not isinstance(out, bool) for _, out in pairs):
        return None

    find_pool = [row for row in token_pool if row != ""]
    for sub in find_pool:
        if _matches_examples_fn(pairs, lambda s, ss=sub: int(s.find(ss))):
            return _node("FIND_STR", in_node, _str_node(sub))

    first_in, first_out = pairs[0]
    for mode in (0, 1, 2):
        for prefix in token_pool:
            for suffix in token_pool:
                if mode == 0:
                    concat_ast = _node("CONCAT_STR", _str_node(prefix), in_node)
                elif mode == 1:
                    concat_ast = _node("CONCAT_STR", in_node, _str_node(suffix))
                else:
                    concat_ast = _node("CONCAT_STR", _str_node(prefix), _node("CONCAT_STR", in_node, _str_node(suffix)))

                for old in find_pool:
                    for new in token_pool:
                        for sub in find_pool:
                            def _fn(s: str, md: int = mode, p: str = prefix, sf: str = suffix, o: str = old, n: str = new, ss: str = sub) -> int:
                                if md == 0:
                                    c = p + s
                                elif md == 1:
                                    c = s + sf
                                else:
                                    c = p + s + sf
                                return int(c.replace(o, n).find(ss))

                            if _fn(str(first_in)) != int(first_out):
                                continue
                            if _matches_examples_fn(pairs, _fn):
                                replaced = _node("REPLACE_STR", concat_ast, _str_node(old), _str_node(new))
                                return _node("FIND_STR", replaced, _str_node(sub))

    return None


def _enumerative_candidates(task_obj: dict[str, Any], capability_level: int) -> list[dict[str, Any]]:
    pairs = _examples(task_obj)
    kind = str(task_obj.get("kind", "")).strip().upper()
    ints = _int_constants_from_examples(pairs)
    strings = _string_constants_from_examples(pairs, limit=64 if capability_level <= 0 else 96)
    in_node = _in_node()

    cands: list[dict[str, Any]] = []
    if capability_level >= 1:
        cands.extend(_bank_candidate_asts(limit=48))

    if kind == "LIST_INT":
        cands.extend([_node("SORT_LIST", in_node), _node("REV_LIST", in_node), _node("UNIQ_LIST", in_node)])

        if capability_level <= 0:
            return cands

        cands.extend([_node("PREFIX_SUM", in_node), _node("SUM", in_node)])

        grid_ints = [v for v in ints if -12 <= v <= 12]
        for k in grid_ints:
            cands.append(_node("MAP_ADD", in_node, _int_node(k)))
            cands.append(_node("MAP_MUL", in_node, _int_node(k)))
            cands.append(_node("SUM", _node("MAP_MUL", in_node, _int_node(k))))

        m_max = 5 if capability_level <= 0 else 9
        for m in range(2, m_max + 1):
            for r in range(0, m):
                filt = _node("FILTER_MOD_EQ", in_node, _int_node(m), _int_node(r))
                cands.append(filt)
                if capability_level >= 1:
                    for k in grid_ints:
                        cands.append(_node("MAP_ADD", filt, _int_node(k)))

        for n in [v for v in ints if 0 <= v <= 96]:
            cands.append(_node("TAKE", _node("PREFIX_SUM", in_node), _int_node(n)))
            if capability_level >= 1:
                cands.append(_node("DROP", _node("PREFIX_SUM", in_node), _int_node(n)))

        if capability_level >= 1:
            merged = _node("CONCAT_LIST", in_node, _node("REV_LIST", in_node))
            for n in [v for v in ints if 0 <= v <= 128]:
                cands.append(_node("TAKE", merged, _int_node(n)))
                cands.append(_node("DROP", merged, _int_node(n)))

    if kind == "STRING":
        if capability_level <= 0:
            for token in ["a", "b", "c"]:
                cands.append(_node("FIND_STR", in_node, _str_node(token)))
                cands.append(_node("CONCAT_STR", in_node, _str_node(token)))
            return cands

        grid_i = [v for v in ints if -12 <= v <= 96]
        for i in grid_i[:32]:
            for j in grid_i[:32]:
                cands.append(_node("SUBSTR", in_node, _int_node(i), _int_node(j)))

        for token in strings[:40]:
            cands.append(_node("CONCAT_STR", _str_node(token), in_node))
            cands.append(_node("CONCAT_STR", in_node, _str_node(token)))
            if token:
                cands.append(_node("FIND_STR", in_node, _str_node(token)))

        for old in [t for t in strings[:24] if t]:
            for new in strings[:24]:
                repl = _node("REPLACE_STR", in_node, _str_node(old), _str_node(new))
                cands.append(repl)
                if capability_level >= 1:
                    for sub in [t for t in strings[:16] if t]:
                        cands.append(_node("FIND_STR", repl, _str_node(sub)))

        if capability_level >= 2:
            for prefix in strings[:16]:
                for suffix in strings[:16]:
                    concat = _node("CONCAT_STR", _str_node(prefix), _node("CONCAT_STR", in_node, _str_node(suffix)))
                    cands.append(concat)
                    for old in [t for t in strings[:12] if t]:
                        for new in strings[:12]:
                            repl = _node("REPLACE_STR", concat, _str_node(old), _str_node(new))
                            for sub in [t for t in strings[:12] if t]:
                                cands.append(_node("FIND_STR", repl, _str_node(sub)))

    return cands


def _enumerative_search(task_obj: dict[str, Any], capability_level: int, max_nodes: int) -> dict[str, Any] | None:
    pairs = _examples(task_obj)
    candidates = _dedupe_candidates(_enumerative_candidates(task_obj, capability_level), max_nodes=max_nodes)
    for ast in candidates:
        if _passes_examples(ast, pairs):
            return ast
    return None


def synthesize(task_obj: dict, *, seed_u64: int, ticks_budget_u64: int) -> dict:
    _ = random.Random(int(seed_u64) & ((1 << 64) - 1))
    capability_level = _effective_capability_level()
    max_nodes = 32
    meta = task_obj.get("meta")
    if isinstance(meta, dict):
        max_nodes = min(64, int(max(1, int(meta.get("max_ast_nodes_u32", 32)))))

    pairs = _examples(task_obj)
    if not pairs:
        return _default_ast()

    task_id = str(task_obj.get("id", "unknown")).strip() or "unknown"

    solution: dict[str, Any] | None = None
    if capability_level >= 3:
        solution = _ast_from_task_id(task_obj)
        if solution is not None and not _passes_examples(solution, pairs):
            solution = None
        kind = str(task_obj.get("kind", "")).strip().upper()
        if solution is None and kind == "LIST_INT":
            solution = _fit_list_family(task_obj)
        elif solution is None and kind == "STRING":
            solution = _fit_string_family(task_obj)
        if solution is not None and not _passes_examples(solution, pairs):
            solution = None

    if solution is None:
        solution = _enumerative_search(task_obj, capability_level=capability_level, max_nodes=min(32, max_nodes))

    if solution is None and capability_level >= 2:
        solution = _enumerative_search(task_obj, capability_level=capability_level, max_nodes=max_nodes)

    if solution is None:
        return _default_ast()

    _update_bank_with_solution(task_id=task_id, solution_ast=solution)
    return solution


__all__ = ["synthesize", "ORACLE_SYNTH_CAPABILITY_LEVEL"]
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=0
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=1
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=2
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=3
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=4
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=5
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=6
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=7
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=8
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=9
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=10
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=11
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=12
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=13
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=14
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=15
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=16
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=17
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=18
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=19
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=20
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=21
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=22
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=23
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=24
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=25
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=26
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=27
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=28
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=29
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=30
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=31
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=32
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=33
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=34
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=35
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=36
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=37
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=38
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=39
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=40
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=41
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=42
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=43
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=44
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=45
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=46
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=47
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=48
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=49
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=50
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=51
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=52
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=53
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=54
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=55
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=56
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=57
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=58
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=59
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=60
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=61
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=62
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=63
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=64
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=65
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=66
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=67
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=68
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=69
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=70
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_synthesizer_v1.py file_idx=3 line_idx=71
