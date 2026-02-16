"""SQLite derived index for the ledger."""

from __future__ import annotations

import sqlite3
from typing import Iterable

from cdel.kernel.types import Type, type_norm


SCHEMA_VERSION = 2


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS modules(
            hash TEXT PRIMARY KEY,
            parent_hash TEXT,
            bytes BLOB,
            cost INT,
            accepted_at INT
        );
        CREATE TABLE IF NOT EXISTS symbols(
            symbol TEXT PRIMARY KEY,
            module_hash TEXT,
            type_norm TEXT,
            def_hash TEXT
        );
        CREATE TABLE IF NOT EXISTS def_hashes(
            symbol TEXT PRIMARY KEY,
            def_hash TEXT,
            module_hash_added TEXT
        );
        CREATE TABLE IF NOT EXISTS deps(
            module_hash TEXT,
            dep_symbol TEXT
        );
        CREATE TABLE IF NOT EXISTS sym_deps(
            symbol TEXT,
            dep_symbol TEXT
        );
        CREATE TABLE IF NOT EXISTS type_index(
            type_norm TEXT,
            symbol TEXT
        );
        CREATE TABLE IF NOT EXISTS aliases(
            symbol TEXT PRIMARY KEY,
            target_symbol TEXT
        );
        CREATE TABLE IF NOT EXISTS concepts(
            concept TEXT,
            symbol TEXT,
            module_hash TEXT,
            PRIMARY KEY(concept, symbol)
        );
        CREATE TABLE IF NOT EXISTS index_impact(
            module_hash TEXT PRIMARY KEY,
            symbols_count INT,
            deps_count INT,
            sym_deps_count INT,
            type_index_count INT,
            def_hashes_count INT
        );
        CREATE TABLE IF NOT EXISTS budget(
            state_id INT PRIMARY KEY,
            remaining INT
        );
        CREATE TABLE IF NOT EXISTS rejections(
            module_hash TEXT,
            reason TEXT,
            details TEXT
        );
        CREATE TABLE IF NOT EXISTS schema_version(
            version INT
        );
        CREATE TABLE IF NOT EXISTS stat_cert_state(
            state_id INT PRIMARY KEY,
            round INT,
            alpha_spent TEXT
        );
        CREATE TABLE IF NOT EXISTS adoptions(
            hash TEXT PRIMARY KEY,
            parent_hash TEXT,
            bytes BLOB,
            accepted_at INT,
            concept TEXT,
            chosen_symbol TEXT,
            baseline_symbol TEXT
        );
        CREATE INDEX IF NOT EXISTS deps_by_symbol ON deps(dep_symbol);
        CREATE INDEX IF NOT EXISTS type_by_type ON type_index(type_norm);
        CREATE INDEX IF NOT EXISTS alias_by_target ON aliases(target_symbol);
        CREATE INDEX IF NOT EXISTS concepts_by_concept ON concepts(concept);
        CREATE INDEX IF NOT EXISTS adoptions_by_concept ON adoptions(concept);
        """
    )
    cur = conn.execute("SELECT version FROM schema_version")
    row = cur.fetchone()
    if row is None:
        conn.execute("INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,))
    elif int(row[0]) != SCHEMA_VERSION:
        raise ValueError("index schema version mismatch; run migration")
    conn.commit()


def symbol_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.execute("SELECT 1 FROM symbols WHERE symbol = ?", (name,))
    return cur.fetchone() is not None


def get_symbol_info(conn: sqlite3.Connection, name: str) -> tuple[str, str] | None:
    cur = conn.execute("SELECT module_hash, type_norm FROM symbols WHERE symbol = ?", (name,))
    row = cur.fetchone()
    if row is None:
        return None
    return row[0], row[1]


def get_symbol_module(conn: sqlite3.Connection, name: str) -> str | None:
    cur = conn.execute("SELECT module_hash FROM symbols WHERE symbol = ?", (name,))
    row = cur.fetchone()
    return None if row is None else row[0]


def get_symbol_type(conn: sqlite3.Connection, name: str) -> str | None:
    cur = conn.execute("SELECT type_norm FROM symbols WHERE symbol = ?", (name,))
    row = cur.fetchone()
    return None if row is None else row[0]


def list_symbol_deps(conn: sqlite3.Connection, name: str) -> list[str]:
    cur = conn.execute("SELECT dep_symbol FROM sym_deps WHERE symbol = ?", (name,))
    return [row[0] for row in cur.fetchall()]


def list_reverse_deps(conn: sqlite3.Connection, name: str, limit: int) -> list[str]:
    cur = conn.execute(
        "SELECT symbol FROM sym_deps WHERE dep_symbol = ? ORDER BY symbol LIMIT ?",
        (name, limit),
    )
    return [row[0] for row in cur.fetchall()]


def list_symbols_for_concept(conn: sqlite3.Connection, concept: str, limit: int) -> list[str]:
    cur = conn.execute(
        "SELECT symbol FROM concepts WHERE concept = ? ORDER BY symbol LIMIT ?",
        (concept, limit),
    )
    return [row[0] for row in cur.fetchall()]


def list_concepts(conn: sqlite3.Connection, limit: int | None = None) -> list[str]:
    if limit is None:
        cur = conn.execute("SELECT DISTINCT concept FROM concepts ORDER BY concept")
    else:
        cur = conn.execute(
            "SELECT DISTINCT concept FROM concepts ORDER BY concept LIMIT ?",
            (limit,),
        )
    return [row[0] for row in cur.fetchall()]


def latest_symbol_for_concept(conn: sqlite3.Connection, concept: str) -> str | None:
    cur = conn.execute(
        "SELECT concepts.symbol FROM concepts "
        "JOIN modules ON modules.hash = concepts.module_hash "
        "WHERE concepts.concept = ? "
        "ORDER BY modules.accepted_at DESC LIMIT 1",
        (concept,),
    )
    row = cur.fetchone()
    return None if row is None else row[0]


def search_symbols_by_type(conn: sqlite3.Connection, type_norm_value: str, limit: int) -> list[str]:
    cur = conn.execute(
        "SELECT symbol FROM type_index WHERE type_norm = ? ORDER BY symbol LIMIT ?",
        (type_norm_value, limit),
    )
    return [row[0] for row in cur.fetchall()]


def search_symbols_by_prefix(conn: sqlite3.Connection, prefix: str, limit: int) -> list[str]:
    cur = conn.execute(
        "SELECT symbol FROM symbols WHERE symbol LIKE ? ORDER BY symbol LIMIT ?",
        (f"{prefix}%", limit),
    )
    return [row[0] for row in cur.fetchall()]


def insert_module(
    conn: sqlite3.Connection,
    module_hash: str,
    parent_hash: str,
    payload_bytes: bytes,
    cost: int,
    accepted_at: int,
) -> None:
    conn.execute(
        "INSERT INTO modules(hash, parent_hash, bytes, cost, accepted_at) VALUES (?, ?, ?, ?, ?)",
        (module_hash, parent_hash, payload_bytes, cost, accepted_at),
    )


def insert_symbols(
    conn: sqlite3.Connection,
    symbol_types: dict[str, Type],
    def_hashes: dict[str, str],
    module_hash: str,
) -> None:
    for name, typ in symbol_types.items():
        conn.execute(
            "INSERT INTO symbols(symbol, module_hash, type_norm, def_hash) VALUES (?, ?, ?, ?)",
            (name, module_hash, type_norm(typ), def_hashes.get(name)),
        )


def insert_def_hashes(conn: sqlite3.Connection, def_hashes: dict[str, str], module_hash: str) -> None:
    for symbol, def_hash in def_hashes.items():
        conn.execute(
            "INSERT INTO def_hashes(symbol, def_hash, module_hash_added) VALUES (?, ?, ?)",
            (symbol, def_hash, module_hash),
        )


def get_def_hash(conn: sqlite3.Connection, symbol: str) -> str | None:
    cur = conn.execute("SELECT def_hash FROM def_hashes WHERE symbol = ?", (symbol,))
    row = cur.fetchone()
    return None if row is None else row[0]


def insert_deps(conn: sqlite3.Connection, module_hash: str, deps: Iterable[str]) -> None:
    for dep in deps:
        conn.execute("INSERT INTO deps(module_hash, dep_symbol) VALUES (?, ?)", (module_hash, dep))


def insert_sym_deps(conn: sqlite3.Connection, symbol: str, deps: Iterable[str]) -> None:
    for dep in deps:
        conn.execute("INSERT INTO sym_deps(symbol, dep_symbol) VALUES (?, ?)", (symbol, dep))


def insert_type_index(conn: sqlite3.Connection, symbol_types: dict[str, Type]) -> None:
    for symbol, typ in symbol_types.items():
        conn.execute(
            "INSERT INTO type_index(type_norm, symbol) VALUES (?, ?)",
            (type_norm(typ), symbol),
        )


def insert_aliases(conn: sqlite3.Connection, alias_map: dict[str, str]) -> None:
    for symbol, target in alias_map.items():
        conn.execute(
            "INSERT INTO aliases(symbol, target_symbol) VALUES (?, ?)",
            (symbol, target),
        )


def get_alias_target(conn: sqlite3.Connection, symbol: str) -> str | None:
    cur = conn.execute("SELECT target_symbol FROM aliases WHERE symbol = ?", (symbol,))
    row = cur.fetchone()
    return None if row is None else row[0]


def list_aliases_for_target(conn: sqlite3.Connection, target: str, limit: int | None = None) -> list[str]:
    sql = "SELECT symbol FROM aliases WHERE target_symbol = ? ORDER BY symbol"
    params: tuple = (target,)
    if limit is not None:
        sql += " LIMIT ?"
        params = (target, limit)
    cur = conn.execute(sql, params)
    return [row[0] for row in cur.fetchall()]


def insert_concepts(conn: sqlite3.Connection, concepts: Iterable[dict], module_hash: str) -> None:
    for entry in concepts:
        if not isinstance(entry, dict):
            continue
        concept = entry.get("concept")
        symbol = entry.get("symbol")
        if concept is None or symbol is None:
            continue
        conn.execute(
            "INSERT INTO concepts(concept, symbol, module_hash) VALUES (?, ?, ?)",
            (concept, symbol, module_hash),
        )


def insert_index_impact(
    conn: sqlite3.Connection,
    module_hash: str,
    symbols_count: int,
    deps_count: int,
    sym_deps_count: int,
    type_index_count: int,
    def_hashes_count: int,
) -> None:
    conn.execute(
        "INSERT INTO index_impact(module_hash, symbols_count, deps_count, sym_deps_count, type_index_count, def_hashes_count) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (module_hash, symbols_count, deps_count, sym_deps_count, type_index_count, def_hashes_count),
    )


def set_budget(conn: sqlite3.Connection, remaining: int) -> None:
    conn.execute("DELETE FROM budget")
    conn.execute("INSERT INTO budget(state_id, remaining) VALUES (1, ?)", (remaining,))


def get_budget(conn: sqlite3.Connection) -> int | None:
    cur = conn.execute("SELECT remaining FROM budget WHERE state_id = 1")
    row = cur.fetchone()
    return None if row is None else int(row[0])


def update_budget(conn: sqlite3.Connection, remaining: int) -> None:
    conn.execute("UPDATE budget SET remaining = ? WHERE state_id = 1", (remaining,))


def get_stat_cert_state(conn: sqlite3.Connection) -> tuple[int, str] | None:
    cur = conn.execute("SELECT round, alpha_spent FROM stat_cert_state WHERE state_id = 1")
    row = cur.fetchone()
    if row is None:
        return None
    return int(row[0]), str(row[1])


def set_stat_cert_state(conn: sqlite3.Connection, round_idx: int, alpha_spent: str) -> None:
    conn.execute("DELETE FROM stat_cert_state")
    conn.execute(
        "INSERT INTO stat_cert_state(state_id, round, alpha_spent) VALUES (1, ?, ?)",
        (round_idx, alpha_spent),
    )


def insert_adoption(
    conn: sqlite3.Connection,
    adoption_hash: str,
    parent_hash: str,
    payload_bytes: bytes,
    accepted_at: int,
    concept: str,
    chosen_symbol: str,
    baseline_symbol: str | None,
) -> None:
    conn.execute(
        "INSERT INTO adoptions(hash, parent_hash, bytes, accepted_at, concept, chosen_symbol, baseline_symbol) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (adoption_hash, parent_hash, payload_bytes, accepted_at, concept, chosen_symbol, baseline_symbol),
    )


def latest_adoption_for_concept(conn: sqlite3.Connection, concept: str) -> dict | None:
    cur = conn.execute(
        "SELECT hash, chosen_symbol, baseline_symbol FROM adoptions "
        "WHERE concept = ? ORDER BY accepted_at DESC LIMIT 1",
        (concept,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return {"hash": row[0], "chosen_symbol": row[1], "baseline_symbol": row[2]}


def concept_symbol_exists(conn: sqlite3.Connection, concept: str, symbol: str) -> bool:
    cur = conn.execute("SELECT 1 FROM concepts WHERE concept = ? AND symbol = ?", (concept, symbol))
    return cur.fetchone() is not None


def record_rejection(conn: sqlite3.Connection, module_hash: str, reason: str, details: str | None) -> None:
    conn.execute(
        "INSERT INTO rejections(module_hash, reason, details) VALUES (?, ?, ?)",
        (module_hash, reason, details),
    )
