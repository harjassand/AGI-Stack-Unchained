"""Library statistics and reuse metrics."""

from __future__ import annotations

from collections import defaultdict

from cdel.config import Config
from cdel.ledger import index as idx


def library_stats(cfg: Config, limit: int = 20) -> dict:
    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)

    cur = conn.execute("SELECT symbol FROM symbols ORDER BY symbol")
    all_symbols = [row[0] for row in cur.fetchall()]

    cur = conn.execute(
        "SELECT dep_symbol, COUNT(1) as c FROM sym_deps GROUP BY dep_symbol ORDER BY c DESC, dep_symbol ASC LIMIT ?",
        (limit,),
    )
    top_dependents = [{"symbol": row[0], "count": int(row[1])} for row in cur.fetchall()]

    cur = conn.execute("SELECT dep_symbol FROM sym_deps")
    used = {row[0] for row in cur.fetchall()}
    unused = [sym for sym in all_symbols if sym not in used]

    deps_map: dict[str, set[str]] = defaultdict(set)
    cur = conn.execute("SELECT symbol, dep_symbol FROM sym_deps")
    for sym, dep in cur.fetchall():
        deps_map[sym].add(dep)

    indegree: dict[str, int] = defaultdict(int)
    for sym, deps in deps_map.items():
        for dep in deps:
            indegree[dep] += 1
        indegree.setdefault(sym, indegree.get(sym, 0))

    outdegree_dist: dict[int, int] = defaultdict(int)
    indegree_dist: dict[int, int] = defaultdict(int)
    for sym in all_symbols:
        outdegree_dist[len(deps_map.get(sym, set()))] += 1
        indegree_dist[indegree.get(sym, 0)] += 1

    cur = conn.execute("SELECT COUNT(1) FROM sym_deps")
    edge_count = int(cur.fetchone()[0])

    depths = _dependency_depths(deps_map, all_symbols)
    depth_distribution: dict[int, int] = defaultdict(int)
    for depth in depths.values():
        depth_distribution[int(depth)] += 1

    return {
        "total_symbols": len(all_symbols),
        "edge_count": edge_count,
        "unused_symbols": unused,
        "dead_ends": unused,
        "top_dependents": top_dependents,
        "indegree_distribution": dict(sorted(indegree_dist.items())),
        "outdegree_distribution": dict(sorted(outdegree_dist.items())),
        "dependency_depth_distribution": dict(sorted(depth_distribution.items())),
    }


def _dependency_depths(deps_map: dict[str, set[str]], symbols: list[str]) -> dict[str, int]:
    memo: dict[str, int] = {}
    visiting: set[str] = set()

    def depth(sym: str) -> int:
        if sym in memo:
            return memo[sym]
        if sym in visiting:
            raise ValueError(f"dependency cycle detected at {sym}")
        visiting.add(sym)
        deps = deps_map.get(sym, set())
        if not deps:
            memo[sym] = 0
        else:
            memo[sym] = 1 + max(depth(dep) for dep in deps)
        visiting.remove(sym)
        return memo[sym]

    for sym in symbols:
        depth(sym)
    return memo
