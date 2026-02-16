"""Ledger lint checks (non-semantic warnings)."""

from __future__ import annotations

import json

from cdel.config import Config
from cdel.ledger import index as idx
from cdel.ledger.storage import iter_order_log, read_meta, read_object


def lint_ledger(cfg: Config, limit: int = 20) -> dict:
    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)

    cur = conn.execute("SELECT symbol FROM symbols ORDER BY symbol")
    all_symbols = [row[0] for row in cur.fetchall()]

    cur = conn.execute("SELECT symbol, dep_symbol FROM sym_deps")
    reverse: dict[str, set[str]] = {}
    for sym, dep in cur.fetchall():
        reverse.setdefault(dep, set()).add(sym)

    unused = [sym for sym in all_symbols if sym not in reverse]

    deprecated = load_deprecated_symbols(cfg)
    deprecated_in_use = []
    for sym in sorted(deprecated):
        users = sorted(reverse.get(sym, set()))
        if not users:
            continue
        replaced_by = deprecated[sym]
        deprecated_in_use.append(
            {
                "symbol": sym,
                "replaced_by": replaced_by,
                "used_by": users[:limit],
                "used_by_count": len(users),
            }
        )

    return {
        "deprecated_in_use": deprecated_in_use,
        "deprecated_in_use_count": len(deprecated_in_use),
        "unused_symbols": unused[:limit],
        "unused_symbol_count": len(unused),
    }


def load_deprecated_symbols(cfg: Config) -> dict[str, str | None]:
    deprecated: dict[str, str | None] = {}
    for module_hash in iter_order_log(cfg):
        meta = read_meta(cfg, module_hash)
        if not meta or not isinstance(meta, dict):
            continue
        if not meta.get("deprecated"):
            continue
        replaced_by = meta.get("replaced_by")
        payload_bytes = read_object(cfg, module_hash)
        payload = json.loads(payload_bytes.decode("utf-8"))
        for sym in payload.get("new_symbols") or []:
            deprecated[sym] = replaced_by if isinstance(replaced_by, str) else None
    return deprecated
