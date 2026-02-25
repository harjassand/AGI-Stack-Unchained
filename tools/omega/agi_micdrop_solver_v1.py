#!/usr/bin/env python3
"""Micdrop solver baseline; intentionally limited in v1."""

from __future__ import annotations

import ast
import json
import math
import re
from typing import Any

# MICDROP_FEATURE:ARITH_V1

_FIB_RE = re.compile(r"^FIB:(\d+)$")
_PRIME_FACT_RE = re.compile(r"^PRIME_FACT:(\d+)$")
_GCD_RE = re.compile(r"^GCD:(-?\d+),(-?\d+)$")
_LCM_RE = re.compile(r"^LCM:(-?\d+),(-?\d+)$")
_DIJKSTRA_RE = re.compile(r"^DIJKSTRA:n=(\d+);edges=([0-9,\-]*);src=(\d+);dst=(\d+)$")
_SAT2CNF_RE = re.compile(r"^SAT2CNF:vars=(\d+);clauses=(.+)$")
_JSON_MINIFY_RE = re.compile(r"^JSON_MINIFY:(.+)$", re.DOTALL)


class _ArithEval(ast.NodeVisitor):
    def visit_Expression(self, node: ast.Expression) -> int | None:  # noqa: N802
        return self.visit(node.body)

    def visit_BinOp(self, node: ast.BinOp) -> int | None:  # noqa: N802
        left = self.visit(node.left)
        right = self.visit(node.right)
        if left is None or right is None:
            return None
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                return None
            if left % right != 0:
                return None
            return left // right
        return None

    def visit_UnaryOp(self, node: ast.UnaryOp) -> int | None:  # noqa: N802
        value = self.visit(node.operand)
        if value is None:
            return None
        if isinstance(node.op, ast.USub):
            return -value
        if isinstance(node.op, ast.UAdd):
            return value
        return None

    def visit_Constant(self, node: ast.Constant) -> int | None:  # noqa: N802
        if isinstance(node.value, bool):
            return None
        if isinstance(node.value, int):
            return int(node.value)
        return None

    def generic_visit(self, node: ast.AST) -> int | None:
        return None


def _solve_arithmetic(prompt: str) -> str | None:
    if not prompt.startswith("Compute:"):
        return None
    expr = prompt.split(":", 1)[1].strip()
    if not expr:
        return None
    try:
        parsed = ast.parse(expr, mode="eval")
    except Exception:  # noqa: BLE001
        return None
    value = _ArithEval().visit(parsed)
    if value is None:
        return None
    return str(value)


def _solve_fib(prompt: str) -> str | None:
    # MICDROP_FEATURE:FIB_V1
    match = _FIB_RE.fullmatch(prompt)
    if match is None:
        return None
    n = int(match.group(1))
    if n < 0 or n > 90:
        return None
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return str(a)


def _solve_prime_factor(prompt: str) -> str | None:
    # MICDROP_FEATURE:PRIME_FACT_V1
    match = _PRIME_FACT_RE.fullmatch(prompt)
    if match is None:
        return None
    value = int(match.group(1))
    if value < 2:
        return None
    n = value
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


def _solve_gcd_lcm(prompt: str) -> str | None:
    # MICDROP_FEATURE:GCD_LCM_V1
    gcd_match = _GCD_RE.fullmatch(prompt)
    if gcd_match is not None:
        left = int(gcd_match.group(1))
        right = int(gcd_match.group(2))
        return str(math.gcd(left, right))
    lcm_match = _LCM_RE.fullmatch(prompt)
    if lcm_match is None:
        return None
    left = int(lcm_match.group(1))
    right = int(lcm_match.group(2))
    if left == 0 or right == 0:
        return "0"
    gcd_value = math.gcd(left, right)
    return str(abs(left // gcd_value * right))


def _solve_dijkstra(prompt: str) -> str | None:
    # MICDROP_FEATURE:DIJKSTRA_V1
    match = _DIJKSTRA_RE.fullmatch(prompt)
    if match is None:
        return None
    n = int(match.group(1))
    edges_blob = match.group(2)
    src = int(match.group(3))
    dst = int(match.group(4))
    if n <= 0 or src < 0 or dst < 0 or src >= n or dst >= n:
        return None
    graph: list[list[tuple[int, int]]] = [[] for _ in range(n)]
    if edges_blob:
        for token in edges_blob.split(","):
            if not token:
                continue
            parts = token.split("-")
            if len(parts) != 3:
                return None
            u = int(parts[0])
            v = int(parts[1])
            weight = int(parts[2])
            if u < 0 or v < 0 or weight < 0 or u >= n or v >= n:
                return None
            graph[u].append((v, weight))
    import heapq

    inf = 10**18
    distances = [inf] * n
    distances[src] = 0
    heap: list[tuple[int, int]] = [(0, src)]
    while heap:
        cur, node = heapq.heappop(heap)
        if cur != distances[node]:
            continue
        if node == dst:
            break
        for nxt, edge_weight in graph[node]:
            candidate = cur + edge_weight
            if candidate < distances[nxt]:
                distances[nxt] = candidate
                heapq.heappush(heap, (candidate, nxt))
    return "INF" if distances[dst] >= inf else str(distances[dst])


def _solve_sat_2cnf(prompt: str) -> str | None:
    # MICDROP_FEATURE:SAT_2CNF_V1
    match = _SAT2CNF_RE.fullmatch(prompt)
    if match is None:
        return None
    vars_count = int(match.group(1))
    clauses_blob = match.group(2).strip()
    if vars_count <= 0 or not clauses_blob:
        return None
    clauses: list[tuple[int, int]] = []
    for token in clauses_blob.split("&"):
        text = token.strip()
        if not (text.startswith("(") and text.endswith(")")):
            return None
        body = text[1:-1]
        if "|" not in body:
            return None
        left_raw, right_raw = body.split("|", 1)
        left = int(left_raw.strip())
        right = int(right_raw.strip())
        if left == 0 or right == 0:
            return None
        if abs(left) > vars_count or abs(right) > vars_count:
            return None
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


def _solve_json_minify(prompt: str) -> str | None:
    # MICDROP_FEATURE:JSON_CANON_MINIFY_V1
    match = _JSON_MINIFY_RE.fullmatch(prompt)
    if match is None:
        return None
    blob = match.group(1).strip()
    if not blob:
        return None
    try:
        value = json.loads(blob)
    except Exception:
        return None
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def solve(prompt: str, *, meta: dict[str, object] | None = None) -> str:
    _ = meta
    text = str(prompt).strip()
    if not text:
        return "UNSOLVED"

    arithmetic = _solve_arithmetic(text)
    if arithmetic is not None:
        return arithmetic

    for handler in (
        _solve_fib,
        _solve_prime_factor,
        _solve_gcd_lcm,
        _solve_dijkstra,
        _solve_sat_2cnf,
        _solve_json_minify,
    ):
        out = handler(text)
        if out is not None:
            return out

    return "UNSOLVED"


__all__ = ["solve"]
