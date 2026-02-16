"""Dependency closure loading."""

from __future__ import annotations

import json
from pathlib import Path

from cdel.kernel.deps import collect_sym_refs
from cdel.kernel.parse import parse_definition
from cdel.kernel.types import Type
from cdel.ledger import index as idx
from cdel.ledger.storage import iter_order_log, read_head, read_object
from cdel.config import Config


def load_module_payload(cfg: Config, module_hash: str) -> dict:
    data = read_object(cfg, module_hash)
    return json.loads(data.decode("utf-8"))


def compute_closure(conn, symbols: list[str]) -> set[str]:
    closure, _ = compute_closure_with_stats(conn, symbols)
    return closure


def compute_closure_with_stats(conn, symbols: list[str]) -> tuple[set[str], int]:
    closure = set(symbols)
    queue = list(symbols)
    lookups = 0
    while queue:
        sym = queue.pop()
        lookups += 1
        for dep in idx.list_symbol_deps(conn, sym):
            if dep not in closure:
                closure.add(dep)
                queue.append(dep)
    return closure, lookups


def load_definitions(cfg: Config, conn, symbols: list[str]) -> dict[str, object]:
    defs, _ = load_definitions_with_stats(cfg, conn, symbols)
    return defs


def load_definitions_with_stats(
    cfg: Config,
    conn,
    symbols: list[str],
    use_cache: bool = False,
) -> tuple[dict[str, object], dict[str, int]]:
    if use_cache and len(symbols) == 1:
        head = read_head(cfg)
        cached = _read_closure_cache(cfg, head, symbols[0])
        if cached:
            defs = _load_defs_from_modules(cfg, cached["modules"])
            stats = {
                "closure_symbols_count": len(cached["symbols"]),
                "closure_modules_count": len(cached["modules"]),
                "scanned_modules_count": 0,
                "index_lookups_count": 0,
                "closure_cache_hits": 1,
                "closure_cache_misses": 0,
            }
            return defs, stats

    closure, dep_lookups = compute_closure_with_stats(conn, symbols)
    defs: dict[str, object] = {}
    loaded_modules: set[str] = set()
    module_lookups = 0
    for sym in closure:
        module_lookups += 1
        module_hash = idx.get_symbol_module(conn, sym)
        if module_hash is None:
            raise ValueError(f"symbol not found in index: {sym}")
        if module_hash in loaded_modules:
            continue
        payload = load_module_payload(cfg, module_hash)
        for defn in payload.get("definitions", []):
            parsed = parse_definition(defn)
            defs[parsed.name] = parsed
        loaded_modules.add(module_hash)
    stats = {
        "closure_symbols_count": len(closure),
        "closure_modules_count": len(loaded_modules),
        "scanned_modules_count": 0,
        "index_lookups_count": dep_lookups + module_lookups,
        "closure_cache_hits": 0,
        "closure_cache_misses": 1 if use_cache and len(symbols) == 1 else 0,
    }
    if use_cache and len(symbols) == 1:
        head = read_head(cfg)
        _write_closure_cache(cfg, head, symbols[0], closure, loaded_modules)
    return defs, stats


def load_definitions_scan_with_stats(cfg: Config, symbols: list[str]) -> tuple[dict[str, object], dict[str, int]]:
    order = iter_order_log(cfg)
    symbol_defs: dict[str, object] = {}
    symbol_deps: dict[str, set[str]] = {}
    symbol_module: dict[str, str] = {}

    for module_hash in order:
        payload = load_module_payload(cfg, module_hash)
        for defn in payload.get("definitions", []):
            name = defn.get("name")
            if not isinstance(name, str):
                continue
            symbol_module[name] = module_hash
            symbol_defs[name] = parse_definition(defn)
            refs = collect_sym_refs(defn.get("body") or {})
            symbol_deps[name] = {s for s in refs if s != name}

    closure = set(symbols)
    queue = list(symbols)
    while queue:
        sym = queue.pop()
        if sym not in symbol_defs:
            raise ValueError(f"symbol not found in ledger scan: {sym}")
        for dep in symbol_deps.get(sym, set()):
            if dep not in closure:
                closure.add(dep)
                queue.append(dep)

    loaded_modules: set[str] = set()
    defs: dict[str, object] = {}
    for sym in closure:
        defs[sym] = symbol_defs[sym]
        module_hash = symbol_module.get(sym)
        if module_hash:
            loaded_modules.add(module_hash)

    stats = {
        "closure_symbols_count": len(closure),
        "closure_modules_count": len(loaded_modules),
        "scanned_modules_count": len(order),
        "index_lookups_count": 0,
        "closure_cache_hits": 0,
        "closure_cache_misses": 0,
    }
    return defs, stats


def _load_defs_from_modules(cfg: Config, module_hashes: list[str]) -> dict[str, object]:
    defs: dict[str, object] = {}
    for module_hash in module_hashes:
        payload = load_module_payload(cfg, module_hash)
        for defn in payload.get("definitions", []):
            parsed = parse_definition(defn)
            defs[parsed.name] = parsed
    return defs


def _closure_cache_path(cfg: Config, head: str, symbol: str) -> Path:
    return cfg.cache_dir / "closure" / head / f"{symbol}.json"


def _read_closure_cache(cfg: Config, head: str, symbol: str) -> dict | None:
    path = _closure_cache_path(cfg, head, symbol)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_closure_cache(cfg: Config, head: str, symbol: str, closure: set[str], modules: set[str]) -> None:
    path = _closure_cache_path(cfg, head, symbol)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"symbols": sorted(closure), "modules": sorted(modules)}
    path.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")


def load_symbol_types(conn, symbols: list[str]) -> dict[str, str]:
    types: dict[str, str] = {}
    for sym in symbols:
        info = idx.get_symbol_info(conn, sym)
        if info is None:
            raise ValueError(f"symbol not found in index: {sym}")
        _, typ = info
        types[sym] = typ
    return types
