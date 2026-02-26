#!/usr/bin/env python3
"""Micdrop solver with capability-gated task-family support."""

from __future__ import annotations

import argparse
import ast
import json
import math
import os
import re
from typing import Any

# MICDROP_CAPABILITY_LEVEL:4
MICDROP_CAPABILITY_LEVEL = 4
def _effective_capability_level() -> int:
    raw = str(os.environ.get("MICDROP_CAPABILITY_LEVEL_OVERRIDE", "")).strip()
    if raw:
        try:
            return max(0, int(raw))
        except Exception:  # noqa: BLE001
            return int(MICDROP_CAPABILITY_LEVEL)
    return int(MICDROP_CAPABILITY_LEVEL)


def _parse_prompt(prompt: str) -> tuple[str, dict[str, str]]:
    text = str(prompt).strip()
    if not text:
        return "", {}
    parts = text.split()
    family = parts[0]
    fields: dict[str, str] = {}
    for token in parts[1:]:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        fields[str(key)] = str(value)
    return family, fields


_COMPUTE_RE = re.compile(r"^Compute:\s*(.+)$")
_FIB_SIMPLE_RE = re.compile(r"^FIB:(\d+)$")
_PRIME_FACT_SIMPLE_RE = re.compile(r"^PRIME_FACT:(\d+)$")
_GCD_SIMPLE_RE = re.compile(r"^GCD:(-?\d+),(-?\d+)$")
_LCM_SIMPLE_RE = re.compile(r"^LCM:(-?\d+),(-?\d+)$")
_DIJKSTRA_SIMPLE_RE = re.compile(r"^DIJKSTRA:n=(\d+);edges=([^;]*);src=(\d+);dst=(\d+)$")
_SAT2_SIMPLE_RE = re.compile(r"^SAT2CNF:vars=(\d+);clauses=(.+)$")
_JSON_MINIFY_SIMPLE_RE = re.compile(r"^JSON_MINIFY:(.+)$", re.DOTALL)


def _eval_arith_expr(expr: str) -> int:
    node = ast.parse(expr, mode="eval")

    def _walk(current: ast.AST) -> int:
        if isinstance(current, ast.Expression):
            return _walk(current.body)
        if isinstance(current, ast.Constant) and isinstance(current.value, int):
            return int(current.value)
        if isinstance(current, ast.UnaryOp) and isinstance(current.op, (ast.UAdd, ast.USub)):
            value = _walk(current.operand)
            return value if isinstance(current.op, ast.UAdd) else -value
        if isinstance(current, ast.BinOp) and isinstance(current.op, (ast.Add, ast.Sub, ast.Mult)):
            left = _walk(current.left)
            right = _walk(current.right)
            if isinstance(current.op, ast.Add):
                return left + right
            if isinstance(current.op, ast.Sub):
                return left - right
            return left * right
        raise ValueError("unsupported arithmetic expression")

    return int(_walk(node))


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
            raise ValueError("CRT moduli are not pairwise coprime")
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
    for a in (2, 7, 61):
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


def _solve_numbertheory(fields: dict[str, str]) -> str:
    op = str(fields.get("op", "")).strip()
    if op == "gcd":
        a = int(fields["a"])
        b = int(fields["b"])
        return str(math.gcd(a, b))
    if op == "lcm":
        a = int(fields["a"])
        b = int(fields["b"])
        g = math.gcd(a, b)
        return str((a // g) * b)
    if op == "modinv":
        a = int(fields["a"])
        m = int(fields["m"])
        inv = _modinv(a, m)
        return "NONE" if inv is None else str(int(inv))
    if op == "crt":
        residues = [int(row) for row in str(fields["residues"]).split(",") if row]
        moduli = [int(row) for row in str(fields["moduli"]).split(",") if row]
        x, mod = _crt_pairwise_coprime(residues, moduli)
        return f"x={x};mod={mod}"
    if op == "isprime":
        n = int(fields["n"])
        return "YES" if _is_prime32(n) else "NO"
    raise ValueError(f"unsupported number theory op: {op}")


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


def _solve_graph(fields: dict[str, str]) -> str:
    op = str(fields.get("op", "")).strip()
    if op != "shortest_path":
        raise ValueError(f"unsupported graph op: {op}")
    n = int(fields["n"])
    src = int(fields["src"])
    dst = int(fields["dst"])
    raw_edges = str(fields.get("edges", "")).strip()
    edges: list[tuple[int, int, int]] = []
    for token in raw_edges.split("|"):
        if not token:
            continue
        u_s, v_s, w_s = token.split(",")
        edges.append((int(u_s), int(v_s), int(w_s)))
    solved = _shortest_path_lex(n=n, src=src, dst=dst, edges=edges)
    if solved is None:
        return "dist=INF;path="
    dist, path = solved
    return f"dist={dist};path={','.join(str(v) for v in path)}"


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


def _solve_string(fields: dict[str, str]) -> str:
    op = str(fields.get("op", "")).strip()
    if op == "edit":
        return str(_edit_distance(str(fields["a"]), str(fields["b"])))
    if op == "lcs":
        return str(_lcs_len(str(fields["a"]), str(fields["b"])))
    if op == "kmp":
        return str(_kmp_first(str(fields["text"]), str(fields["pattern"])))
    if op == "regex":
        return "YES" if _regex_match_subset(str(fields["text"]), str(fields["pattern"])) else "NO"
    raise ValueError(f"unsupported string op: {op}")


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
        raise ValueError(f"unsupported DSL op: {op}")
    return int(x), int(steps), bool(halted)


def _solve_dsl(fields: dict[str, str]) -> str:
    op = str(fields.get("op", "")).strip()
    if op != "execute":
        raise ValueError(f"unsupported DSL op: {op}")
    program = [token for token in str(fields.get("program", "")).split("|") if token]
    x, steps, halted = _exec_dsl(program, step_limit=10_000)
    if not halted:
        return "x=TIMEOUT;steps=10000"
    return f"x={x};steps={steps}"


def _solve_fib_simple(n: int) -> str:
    if n < 0 or n > 90:
        raise ValueError("fib out of range")
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return str(a)


def _solve_prime_factor_simple(value: int) -> str:
    if value < 2:
        raise ValueError("prime factor input must be >= 2")
    n = int(value)
    factors: list[tuple[int, int]] = []
    divisor = 2
    while divisor * divisor <= n:
        count = 0
        while n % divisor == 0:
            n //= divisor
            count += 1
        if count:
            factors.append((divisor, count))
        divisor += 1
    if n > 1:
        factors.append((n, 1))
    return "*".join(f"{prime}^{exp}" for prime, exp in factors)


def _solve_dijkstra_simple(text: str) -> str:
    match = _DIJKSTRA_SIMPLE_RE.fullmatch(text)
    if match is None:
        raise ValueError("invalid dijkstra prompt")
    n = int(match.group(1))
    raw_edges = str(match.group(2)).strip()
    src = int(match.group(3))
    dst = int(match.group(4))
    edges: list[tuple[int, int, int]] = []
    if raw_edges:
        for token in raw_edges.split(","):
            u_s, v_s, w_s = token.split("-")
            edges.append((int(u_s), int(v_s), int(w_s)))
    solved = _shortest_path_lex(n=n, src=src, dst=dst, edges=edges)
    if solved is None:
        return "INF"
    dist, _path = solved
    return str(dist)


def _solve_sat2_simple(text: str) -> str:
    match = _SAT2_SIMPLE_RE.fullmatch(text)
    if match is None:
        raise ValueError("invalid sat2cnf prompt")
    vars_count = int(match.group(1))
    clauses_blob = str(match.group(2)).strip()
    if vars_count <= 0 or not clauses_blob:
        raise ValueError("invalid sat2cnf params")

    clauses: list[tuple[int, int]] = []
    for token in clauses_blob.split("&"):
        body = token.strip()
        if not (body.startswith("(") and body.endswith(")")):
            raise ValueError("invalid clause format")
        left_raw, right_raw = body[1:-1].split("|", 1)
        left = int(left_raw.strip())
        right = int(right_raw.strip())
        if left == 0 or right == 0:
            raise ValueError("literal 0 not allowed")
        if abs(left) > vars_count or abs(right) > vars_count:
            raise ValueError("literal out of range")
        clauses.append((left, right))

    size = vars_count * 2
    graph: list[list[int]] = [[] for _ in range(size)]
    reverse_graph: list[list[int]] = [[] for _ in range(size)]

    def idx(lit: int) -> int:
        var = abs(lit) - 1
        return 2 * var + (0 if lit > 0 else 1)

    def neg(node: int) -> int:
        return node ^ 1

    for left, right in clauses:
        left_idx = idx(left)
        right_idx = idx(right)
        not_left = neg(left_idx)
        not_right = neg(right_idx)
        graph[not_left].append(right_idx)
        graph[not_right].append(left_idx)
        reverse_graph[right_idx].append(not_left)
        reverse_graph[left_idx].append(not_right)

    order: list[int] = []
    seen = [False] * size

    def dfs(node: int) -> None:
        seen[node] = True
        for nxt in graph[node]:
            if not seen[nxt]:
                dfs(nxt)
        order.append(node)

    for node in range(size):
        if not seen[node]:
            dfs(node)

    comp = [-1] * size

    def reverse_dfs(node: int, color: int) -> None:
        comp[node] = color
        for nxt in reverse_graph[node]:
            if comp[nxt] == -1:
                reverse_dfs(nxt, color)

    color = 0
    for node in reversed(order):
        if comp[node] == -1:
            reverse_dfs(node, color)
            color += 1

    for var in range(vars_count):
        if comp[2 * var] == comp[2 * var + 1]:
            return "UNSAT"
    return "SAT"


def _solve_holdout_prompt(*, text: str, capability: int) -> str | None:
    compute_match = _COMPUTE_RE.fullmatch(text)
    if compute_match is not None:
        expr = str(compute_match.group(1)).strip()
        return str(_eval_arith_expr(expr))

    fib_match = _FIB_SIMPLE_RE.fullmatch(text)
    if fib_match is not None:
        if capability < 1:
            return "UNSUPPORTED"
        return _solve_fib_simple(int(fib_match.group(1)))

    prime_match = _PRIME_FACT_SIMPLE_RE.fullmatch(text)
    if prime_match is not None:
        if capability < 1:
            return "UNSUPPORTED"
        return _solve_prime_factor_simple(int(prime_match.group(1)))

    gcd_match = _GCD_SIMPLE_RE.fullmatch(text)
    if gcd_match is not None:
        if capability < 1:
            return "UNSUPPORTED"
        return str(math.gcd(int(gcd_match.group(1)), int(gcd_match.group(2))))

    lcm_match = _LCM_SIMPLE_RE.fullmatch(text)
    if lcm_match is not None:
        if capability < 1:
            return "UNSUPPORTED"
        left = int(lcm_match.group(1))
        right = int(lcm_match.group(2))
        if left == 0 or right == 0:
            return "0"
        gcd_value = math.gcd(left, right)
        return str(abs(left // gcd_value * right))

    if _DIJKSTRA_SIMPLE_RE.fullmatch(text) is not None:
        if capability < 2:
            return "UNSUPPORTED"
        return _solve_dijkstra_simple(text)

    if _SAT2_SIMPLE_RE.fullmatch(text) is not None:
        if capability < 3:
            return "UNSUPPORTED"
        return _solve_sat2_simple(text)

    json_match = _JSON_MINIFY_SIMPLE_RE.fullmatch(text)
    if json_match is not None:
        if capability < 4:
            return "UNSUPPORTED"
        blob = str(json_match.group(1)).strip()
        value = json.loads(blob)
        return json.dumps(value, sort_keys=True, separators=(",", ":"))

    return None


def solve_prompt(prompt: str, meta: dict[str, Any] | None = None) -> str:
    capability = _effective_capability_level()
    text = str(prompt).strip()
    family, fields = _parse_prompt(text)
    try:
        direct = _solve_holdout_prompt(text=text, capability=capability)
        if direct is not None:
            return direct
        if family == "ARITH":
            return str(_eval_arith_expr(str(fields["expr"])))
        if family == "NUMTHEORY":
            if capability < 1:
                return "UNSUPPORTED"
            return _solve_numbertheory(fields)
        if family == "GRAPH":
            if capability < 2:
                return "UNSUPPORTED"
            return _solve_graph(fields)
        if family == "STRING":
            if capability < 3:
                return "UNSUPPORTED"
            return _solve_string(fields)
        if family == "DSL":
            if capability < 4:
                return "UNSUPPORTED"
            return _solve_dsl(fields)
    except Exception:  # noqa: BLE001
        return "UNSUPPORTED"
    return "UNSUPPORTED"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="agi_micdrop_solver_v1")
    parser.add_argument("--prompt", required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    print(solve_prompt(str(args.prompt)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=0
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=1
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=2
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=3
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=4
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=5
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=6
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=7
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=8
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=9
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=10
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=11
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=12
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=13
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=14
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=15
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=16
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=17
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=18
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=19
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=20
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=21
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=22
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=23
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=24
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=25
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=26
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=27
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=28
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=29
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=30
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=31
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=32
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=33
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=34
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=35
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=36
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=37
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=38
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=39
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=40
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=41
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=42
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=43
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=44
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=45
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=46
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=47
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=48
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=49
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=50
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=51
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=52
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=53
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=54
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=55
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=56
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=57
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=58
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=59
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=60
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=61
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=62
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=63
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=64
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=65
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=66
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=67
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=68
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=69
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=70
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/agi_micdrop_solver_v1.py file_idx=0 line_idx=71
