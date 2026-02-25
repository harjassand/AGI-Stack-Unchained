#!/usr/bin/env python3
"""Deterministic micdrop novelty holdout pack generator (v1)."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
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

_SUITES = ("arith", "numbertheory", "graph", "string", "dsl")
_SUITE_PREFIX = {
    "arith": "ARITH",
    "numbertheory": "NUMTH",
    "graph": "GRAPH",
    "string": "STRING",
    "dsl": "DSL",
}


def _ensure_u64(value: int) -> int:
    out = int(value)
    if out < 0 or out >= (1 << 64):
        raise ValueError("seed_u64 must be in [0, 2^64)")
    return out


def _suite_rng(seed_u64: int, suite: str, n: int) -> random.Random:
    digest = hashlib.sha256(f"{int(seed_u64)}|{suite}|{int(n)}|micdrop_novelty_packgen_v1".encode("utf-8")).hexdigest()
    seed = int(digest[:16], 16)
    return random.Random(seed)


def _pack_store_root() -> Path:
    return (_REPO_ROOT / "authority" / "holdouts" / "packs").resolve()


def _write_pack(payload_no_id: dict[str, Any]) -> str:
    payload = dict(payload_no_id)
    payload.pop("pack_id", None)
    pack_id = canon_hash_obj(payload)
    payload["pack_id"] = pack_id
    digest = pack_id.split(":", 1)[1]
    path = _pack_store_root() / f"sha256_{digest}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(path, payload)
    return pack_id


def _arith_expr(rng: random.Random, depth: int) -> tuple[str, int]:
    if depth <= 0 or rng.random() < 0.34:
        value = rng.randint(10**8, 10**14)
        if rng.random() < 0.20:
            value = -value
        return str(int(value)), int(value)
    left_expr, left_val = _arith_expr(rng, depth - 1)
    right_expr, right_val = _arith_expr(rng, depth - 1)
    op = rng.choice(["+", "-", "*"])
    if op == "+":
        value = left_val + right_val
    elif op == "-":
        value = left_val - right_val
    else:
        value = left_val * right_val
    return f"({left_expr}{op}{right_expr})", int(value)


def _egcd(a: int, b: int) -> tuple[int, int, int]:
    x0, y0, x1, y1 = 1, 0, 0, 1
    aa, bb = abs(a), abs(b)
    while bb:
        q = aa // bb
        aa, bb = bb, aa - q * bb
        x0, x1 = x1, x0 - q * x1
        y0, y1 = y1, y0 - q * y1
    g = aa
    return g, x0 if a >= 0 else -x0, y0 if b >= 0 else -y0


def _modinv(a: int, m: int) -> int | None:
    if m <= 0:
        return None
    g, x, _ = _egcd(a, m)
    if g != 1:
        return None
    return x % m


def _crt_pairwise_coprime(residues: list[int], moduli: list[int]) -> tuple[int, int]:
    x = 0
    mod = 1
    for r_i, m_i in zip(residues, moduli):
        inv = _modinv(mod % m_i, m_i)
        if inv is None:
            raise ValueError("moduli must be pairwise coprime")
        t = ((r_i - x) % m_i) * inv % m_i
        x += mod * t
        mod *= m_i
        x %= mod
    return int(x), int(mod)


def _is_prime32(n: int) -> bool:
    if n < 2:
        return False
    small = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29)
    for p in small:
        if n == p:
            return True
        if n % p == 0:
            return False
    d = n - 1
    s = 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for a in (2, 7, 61):  # deterministic for 32-bit integers
        if a % n == 0:
            continue
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        witness = True
        for _ in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                witness = False
                break
        if witness:
            return False
    return True


def _shortest_path_lex(*, n: int, src: int, dst: int, edges: list[tuple[int, int, int]]) -> tuple[int, list[int]] | None:
    adjacency: list[list[tuple[int, int]]] = [[] for _ in range(n)]
    for u, v, w in edges:
        adjacency[u].append((v, w))
    for row in adjacency:
        row.sort(key=lambda x: (x[0], x[1]))

    inf = 10**30
    best_dist = [inf] * n
    best_path: list[tuple[int, ...] | None] = [None] * n
    best_dist[src] = 0
    best_path[src] = (src,)

    import heapq

    heap: list[tuple[int, tuple[int, ...], int]] = [(0, (src,), src)]
    while heap:
        dist_u, path_u, u = heapq.heappop(heap)
        if dist_u != best_dist[u]:
            continue
        if best_path[u] != path_u:
            continue
        for v, w in adjacency[u]:
            nd = dist_u + w
            np = path_u + (v,)
            curd = best_dist[v]
            curp = best_path[v]
            if nd < curd or (nd == curd and (curp is None or np < curp)):
                best_dist[v] = nd
                best_path[v] = np
                heapq.heappush(heap, (nd, np, v))
    if best_path[dst] is None:
        return None
    return int(best_dist[dst]), list(best_path[dst] or ())


def _edit_distance(a: str, b: str) -> int:
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            cur = dp[j]
            if a[i - 1] == b[j - 1]:
                dp[j] = prev
            else:
                dp[j] = min(prev, dp[j], dp[j - 1]) + 1
            prev = cur
    return int(dp[n])


def _lcs_len(a: str, b: str) -> int:
    m, n = len(a), len(b)
    dp = [0] * (n + 1)
    for i in range(1, m + 1):
        prev = 0
        for j in range(1, n + 1):
            cur = dp[j]
            if a[i - 1] == b[j - 1]:
                dp[j] = prev + 1
            else:
                dp[j] = max(dp[j], dp[j - 1])
            prev = cur
    return int(dp[n])


def _kmp_first(text: str, pattern: str) -> int:
    if pattern == "":
        return 0
    lps = [0] * len(pattern)
    k = 0
    for i in range(1, len(pattern)):
        while k > 0 and pattern[i] != pattern[k]:
            k = lps[k - 1]
        if pattern[i] == pattern[k]:
            k += 1
            lps[i] = k
    k = 0
    for idx, ch in enumerate(text):
        while k > 0 and ch != pattern[k]:
            k = lps[k - 1]
        if ch == pattern[k]:
            k += 1
            if k == len(pattern):
                return idx - len(pattern) + 1
    return -1


def _regex_match_subset(text: str, pattern: str) -> bool:
    m, n = len(text), len(pattern)
    dp = [[False] * (n + 1) for _ in range(m + 1)]
    dp[m][n] = True
    for j in range(n - 1, -1, -1):
        if j + 1 < n and pattern[j + 1] == "*":
            dp[m][j] = dp[m][j + 2]
    for i in range(m, -1, -1):
        for j in range(n - 1, -1, -1):
            first = i < m and (pattern[j] == "." or pattern[j] == text[i])
            if j + 1 < n and pattern[j + 1] == "*":
                dp[i][j] = dp[i][j + 2] or (first and dp[i + 1][j])
            elif i < m:
                dp[i][j] = first and dp[i + 1][j + 1]
    return bool(dp[0][0])


def _parse_dsl_instr(raw: str) -> tuple[str, tuple[Any, ...]]:
    parts = raw.split(":")
    op = parts[0]
    if op == "SET" and len(parts) == 3 and parts[1] == "x":
        return "SET", (int(parts[2]),)
    if op == "ADD" and len(parts) == 3 and parts[1] == "x":
        return "ADD", (int(parts[2]),)
    if op == "MUL" and len(parts) == 3 and parts[1] == "x":
        return "MUL", (int(parts[2]),)
    if op == "IF" and len(parts) == 5 and parts[1] == "x" and parts[3] == "GOTO":
        return "IF", (int(parts[2]), str(parts[4]))
    if op == "LABEL" and len(parts) == 2:
        return "LABEL", (str(parts[1]),)
    if op == "HALT" and len(parts) == 1:
        return "HALT", ()
    raise ValueError(f"invalid DSL instruction: {raw}")


def _exec_dsl(program: list[str], *, step_limit: int = 10_000) -> tuple[int, int, bool]:
    parsed = [_parse_dsl_instr(row) for row in program]
    labels: dict[str, int] = {}
    for idx, (op, args) in enumerate(parsed):
        if op == "LABEL":
            labels[str(args[0])] = idx
    x = 0
    pc = 0
    steps = 0
    halted = False
    while 0 <= pc < len(parsed) and steps < int(step_limit):
        steps += 1
        op, args = parsed[pc]
        if op == "HALT":
            halted = True
            break
        if op == "LABEL":
            pc += 1
            continue
        if op == "SET":
            x = int(args[0])
            pc += 1
            continue
        if op == "ADD":
            x += int(args[0])
            pc += 1
            continue
        if op == "MUL":
            x *= int(args[0])
            pc += 1
            continue
        if op == "IF":
            bound = int(args[0])
            label = str(args[1])
            if x < bound:
                if label not in labels:
                    raise ValueError(f"unknown DSL label: {label}")
                pc = labels[label]
            else:
                pc += 1
            continue
        raise ValueError(f"unknown DSL op: {op}")
    return int(x), int(steps), bool(halted)


def _rand_word(rng: random.Random, min_len: int, max_len: int, *, alphabet: str) -> str:
    length = rng.randint(min_len, max_len)
    return "".join(rng.choice(alphabet) for _ in range(length))


def _rand_regex_pattern(rng: random.Random) -> str:
    atoms = rng.randint(1, 10)
    out: list[str] = []
    for _ in range(atoms):
        ch = rng.choice(["a", "b", "c", ".", "d"])
        if rng.random() < 0.35:
            out.append(ch + "*")
        else:
            out.append(ch)
    return "".join(out) or "a*"


def _gen_arith_rows(*, seed_u64: int, n: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rng = _suite_rng(seed_u64, "arith", n)
    inputs: list[dict[str, Any]] = []
    labels: list[dict[str, Any]] = []
    for idx in range(int(n)):
        expr, value = _arith_expr(rng, depth=rng.randint(2, 5))
        row_id = f"{_SUITE_PREFIX['arith']}-{idx:06d}"
        inputs.append(
            {
                "id": row_id,
                "prompt": f"ARITH expr={expr}",
                "meta": {
                    "suite": "arith",
                    "seed_u64": int(seed_u64),
                    "index_u64": int(idx),
                },
            }
        )
        labels.append({"id": row_id, "label": str(int(value))})
    return inputs, labels


def _gen_numbertheory_rows(*, seed_u64: int, n: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rng = _suite_rng(seed_u64, "numbertheory", n)
    ops = ["gcd", "lcm", "modinv", "crt", "isprime"]
    inputs: list[dict[str, Any]] = []
    labels: list[dict[str, Any]] = []
    for idx in range(int(n)):
        op = ops[idx % len(ops)]
        row_id = f"{_SUITE_PREFIX['numbertheory']}-{idx:06d}"
        if op == "gcd":
            a = rng.randint(1, 10**14)
            b = rng.randint(1, 10**14)
            label = str(math.gcd(a, b))
            prompt = f"NUMTHEORY op=gcd a={a} b={b}"
            meta: dict[str, Any] = {"op": op, "a": int(a), "b": int(b)}
        elif op == "lcm":
            a = rng.randint(1, 10**12)
            b = rng.randint(1, 10**12)
            g = math.gcd(a, b)
            label = str((a // g) * b)
            prompt = f"NUMTHEORY op=lcm a={a} b={b}"
            meta = {"op": op, "a": int(a), "b": int(b)}
        elif op == "modinv":
            m = rng.randint(2, 2**31 - 1)
            a = rng.randint(1, m - 1)
            inv = _modinv(a, m)
            label = "NONE" if inv is None else str(int(inv))
            prompt = f"NUMTHEORY op=modinv a={a} m={m}"
            meta = {"op": op, "a": int(a), "m": int(m)}
        elif op == "crt":
            k = rng.randint(2, 4)
            moduli: list[int] = []
            while len(moduli) < k:
                m = rng.randint(101, 997)
                if not _is_prime32(m):
                    continue
                if all(math.gcd(m, existing) == 1 for existing in moduli):
                    moduli.append(int(m))
            residues = [rng.randint(0, m - 1) for m in moduli]
            x, mod = _crt_pairwise_coprime(residues, moduli)
            residues_text = ",".join(str(v) for v in residues)
            moduli_text = ",".join(str(v) for v in moduli)
            label = f"x={int(x)};mod={int(mod)}"
            prompt = f"NUMTHEORY op=crt residues={residues_text} moduli={moduli_text}"
            meta = {"op": op, "residues": residues, "moduli": moduli}
        else:
            n32 = rng.getrandbits(32)
            if n32 < 2:
                n32 += 2
            label = "YES" if _is_prime32(int(n32)) else "NO"
            prompt = f"NUMTHEORY op=isprime n={int(n32)}"
            meta = {"op": op, "n": int(n32)}

        inputs.append(
            {
                "id": row_id,
                "prompt": prompt,
                "meta": {
                    "suite": "numbertheory",
                    "seed_u64": int(seed_u64),
                    "index_u64": int(idx),
                    **meta,
                },
            }
        )
        labels.append({"id": row_id, "label": label})
    return inputs, labels


def _generate_graph_case(rng: random.Random) -> tuple[int, int, int, list[tuple[int, int, int]], int, list[int]]:
    for _ in range(64):
        n = rng.randint(8, 40)
        src = rng.randrange(n)
        dst = rng.randrange(n)
        while dst == src:
            dst = rng.randrange(n)

        edges_map: dict[tuple[int, int], int] = {}
        mids = [node for node in range(n) if node not in {src, dst}]
        rng.shuffle(mids)
        chain_len = rng.randint(0, min(5, len(mids)))
        chain = [src] + mids[:chain_len] + [dst]
        for u, v in zip(chain, chain[1:]):
            w = rng.randint(1, 40)
            edges_map[(u, v)] = min(w, edges_map.get((u, v), w))

        target_edges = rng.randint(n + 4, min(n * (n - 1), n * 8))
        while len(edges_map) < target_edges:
            u = rng.randrange(n)
            v = rng.randrange(n)
            if u == v:
                continue
            w = rng.randint(1, 60)
            key = (u, v)
            if key not in edges_map:
                edges_map[key] = int(w)
            else:
                edges_map[key] = min(edges_map[key], int(w))

        edges = [(u, v, w) for (u, v), w in sorted(edges_map.items(), key=lambda row: (row[0][0], row[0][1], row[1]))]
        answer = _shortest_path_lex(n=n, src=src, dst=dst, edges=edges)
        if answer is None:
            continue
        dist, path = answer
        return int(n), int(src), int(dst), edges, int(dist), path
    raise RuntimeError("failed to generate connected graph case")


def _gen_graph_rows(*, seed_u64: int, n: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rng = _suite_rng(seed_u64, "graph", n)
    inputs: list[dict[str, Any]] = []
    labels: list[dict[str, Any]] = []
    for idx in range(int(n)):
        n_nodes, src, dst, edges, dist, path = _generate_graph_case(rng)
        row_id = f"{_SUITE_PREFIX['graph']}-{idx:06d}"
        edges_text = "|".join(f"{u},{v},{w}" for u, v, w in edges)
        prompt = f"GRAPH op=shortest_path n={n_nodes} src={src} dst={dst} edges={edges_text}"
        label = f"dist={dist};path={','.join(str(v) for v in path)}"
        inputs.append(
            {
                "id": row_id,
                "prompt": prompt,
                "meta": {
                    "suite": "graph",
                    "seed_u64": int(seed_u64),
                    "index_u64": int(idx),
                    "n": int(n_nodes),
                    "src": int(src),
                    "dst": int(dst),
                },
            }
        )
        labels.append({"id": row_id, "label": label})
    return inputs, labels


def _gen_string_rows(*, seed_u64: int, n: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rng = _suite_rng(seed_u64, "string", n)
    ops = ["edit", "lcs", "kmp", "regex"]
    inputs: list[dict[str, Any]] = []
    labels: list[dict[str, Any]] = []
    for idx in range(int(n)):
        op = ops[idx % len(ops)]
        row_id = f"{_SUITE_PREFIX['string']}-{idx:06d}"
        if op == "edit":
            a = _rand_word(rng, 4, 16, alphabet="abcdef")
            b = _rand_word(rng, 4, 16, alphabet="abcdef")
            prompt = f"STRING op=edit a={a} b={b}"
            label = str(_edit_distance(a, b))
            meta: dict[str, Any] = {"op": op, "a": a, "b": b}
        elif op == "lcs":
            a = _rand_word(rng, 5, 20, alphabet="abcxyz")
            b = _rand_word(rng, 5, 20, alphabet="abcxyz")
            prompt = f"STRING op=lcs a={a} b={b}"
            label = str(_lcs_len(a, b))
            meta = {"op": op, "a": a, "b": b}
        elif op == "kmp":
            text = _rand_word(rng, 20, 64, alphabet="abcde")
            if rng.random() < 0.6:
                start = rng.randint(0, max(0, len(text) - 2))
                end = min(len(text), start + rng.randint(1, 8))
                pattern = text[start:end]
            else:
                pattern = _rand_word(rng, 1, 8, alphabet="abcde")
            prompt = f"STRING op=kmp text={text} pattern={pattern}"
            label = str(_kmp_first(text, pattern))
            meta = {"op": op, "text": text, "pattern": pattern}
        else:
            text = _rand_word(rng, 0, 18, alphabet="abcd")
            pattern = _rand_regex_pattern(rng)
            prompt = f"STRING op=regex text={text} pattern={pattern}"
            label = "YES" if _regex_match_subset(text, pattern) else "NO"
            meta = {"op": op, "text": text, "pattern": pattern}

        inputs.append(
            {
                "id": row_id,
                "prompt": prompt,
                "meta": {
                    "suite": "string",
                    "seed_u64": int(seed_u64),
                    "index_u64": int(idx),
                    **meta,
                },
            }
        )
        labels.append({"id": row_id, "label": label})
    return inputs, labels


def _build_dsl_program(rng: random.Random) -> list[str]:
    start = rng.randint(-20, 20)
    first_bound = rng.randint(8, 120)
    first_step = rng.randint(1, 6)
    rows = [
        f"SET:x:{start}",
        "LABEL:L0",
        f"ADD:x:{first_step}",
        f"IF:x:{first_bound}:GOTO:L0",
    ]
    if rng.random() < 0.7:
        rows.append(f"MUL:x:{rng.randint(1, 5)}")
    if rng.random() < 0.8:
        rows.append(f"ADD:x:{rng.randint(-40, 40)}")
    if rng.random() < 0.45:
        second_bound = first_bound + rng.randint(2, 80)
        second_step = rng.randint(1, 4)
        rows.extend(
            [
                "LABEL:L1",
                f"ADD:x:{second_step}",
                f"IF:x:{second_bound}:GOTO:L1",
            ]
        )
    rows.append("HALT")
    return rows


def _gen_dsl_rows(*, seed_u64: int, n: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rng = _suite_rng(seed_u64, "dsl", n)
    inputs: list[dict[str, Any]] = []
    labels: list[dict[str, Any]] = []
    for idx in range(int(n)):
        for _ in range(64):
            program = _build_dsl_program(rng)
            x, steps, halted = _exec_dsl(program, step_limit=10_000)
            if halted and steps <= 10_000:
                break
        else:
            raise RuntimeError("failed to generate halting DSL program")
        row_id = f"{_SUITE_PREFIX['dsl']}-{idx:06d}"
        program_text = "|".join(program)
        prompt = f"DSL op=execute semantics=if_lt program={program_text}"
        label = f"x={x};steps={steps}"
        inputs.append(
            {
                "id": row_id,
                "prompt": prompt,
                "meta": {
                    "suite": "dsl",
                    "seed_u64": int(seed_u64),
                    "index_u64": int(idx),
                    "semantics": "if_lt",
                },
            }
        )
        labels.append({"id": row_id, "label": label})
    return inputs, labels


def _build_rows(*, suite: str, seed_u64: int, n: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if suite == "arith":
        return _gen_arith_rows(seed_u64=seed_u64, n=n)
    if suite == "numbertheory":
        return _gen_numbertheory_rows(seed_u64=seed_u64, n=n)
    if suite == "graph":
        return _gen_graph_rows(seed_u64=seed_u64, n=n)
    if suite == "string":
        return _gen_string_rows(seed_u64=seed_u64, n=n)
    if suite == "dsl":
        return _gen_dsl_rows(seed_u64=seed_u64, n=n)
    raise ValueError(f"unsupported suite: {suite}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="micdrop_novelty_packgen_v1")
    parser.add_argument("--seed_u64", type=int, required=True)
    parser.add_argument("--suite", choices=list(_SUITES), required=True)
    parser.add_argument("--n", type=int, required=True)
    parser.add_argument("--out_dir", required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    seed_u64 = _ensure_u64(int(args.seed_u64))
    suite = str(args.suite).strip()
    n = int(args.n)
    if n <= 0:
        raise ValueError("n must be positive")

    out_dir = Path(str(args.out_dir)).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    inputs_rows, labels_rows = _build_rows(suite=suite, seed_u64=seed_u64, n=n)
    inputs_pack_id = _write_pack(
        {
            "schema_version": "holdout_pack_v1",
            "pack_kind": "inputs",
            "suite": suite,
            "seed_u64": int(seed_u64),
            "rows": inputs_rows,
        }
    )
    labels_pack_id = _write_pack(
        {
            "schema_version": "holdout_pack_v1",
            "pack_kind": "labels",
            "suite": suite,
            "seed_u64": int(seed_u64),
            "rows": labels_rows,
        }
    )

    summary = {
        "suite": suite,
        "inputs_pack_id": inputs_pack_id,
        "labels_pack_id": labels_pack_id,
    }
    (out_dir / f"{suite}_packs.json").write_text(
        json.dumps(summary, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
