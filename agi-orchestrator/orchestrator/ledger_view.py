"""Read-only view over the CDEL index."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from orchestrator.types import AdoptionInfo, SignatureInfo, SymbolInfo


class LedgerView:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        self.index_path = root_dir / "index" / "index.sqlite"

    def get_symbols_for_concept(self, concept: str, limit: int = 20) -> list[SymbolInfo]:
        if not self.index_path.exists():
            return []
        with sqlite3.connect(self.index_path) as conn:
            cur = conn.execute(
                "SELECT symbols.symbol, symbols.type_norm, symbols.module_hash "
                "FROM concepts JOIN symbols ON symbols.symbol = concepts.symbol "
                "WHERE concepts.concept = ? ORDER BY symbols.symbol LIMIT ?",
                (concept, limit),
            )
            rows = cur.fetchall()
        return [SymbolInfo(name=row[0], type_norm=row[1], module_hash=row[2]) for row in rows]

    def get_symbol_signature(self, symbol: str) -> SignatureInfo | None:
        if not self.index_path.exists():
            return None
        with sqlite3.connect(self.index_path) as conn:
            cur = conn.execute("SELECT type_norm FROM symbols WHERE symbol = ?", (symbol,))
            row = cur.fetchone()
        if row is None:
            return None
        return SignatureInfo(symbol=symbol, type_norm=str(row[0]))

    def get_symbol_deps(self, symbol: str) -> list[str]:
        if not self.index_path.exists():
            return []
        with sqlite3.connect(self.index_path) as conn:
            cur = conn.execute("SELECT dep_symbol FROM sym_deps WHERE symbol = ?", (symbol,))
            rows = cur.fetchall()
        return [row[0] for row in rows]

    def get_symbols_by_type(self, type_norm: str, limit: int = 20) -> list[str]:
        if not self.index_path.exists():
            return []
        with sqlite3.connect(self.index_path) as conn:
            cur = conn.execute(
                "SELECT symbol FROM type_index WHERE type_norm = ? ORDER BY symbol LIMIT ?",
                (type_norm, limit),
            )
            rows = cur.fetchall()
        return [row[0] for row in rows]

    def get_type_compatible_symbols(self, type_norm: str, limit: int = 20) -> list[str]:
        if not self.index_path.exists():
            return []
        with sqlite3.connect(self.index_path) as conn:
            cur = conn.execute("SELECT symbol, type_norm FROM symbols ORDER BY symbol")
            rows = cur.fetchall()
        scored: list[tuple[int, str]] = []
        for symbol, cand_type in rows:
            score = _type_compat_score(type_norm, cand_type)
            if score > 0:
                scored.append((score, symbol))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [symbol for _, symbol in scored[:limit]]

    def get_recent_adoptions(self, concept: str, limit: int = 5) -> list[AdoptionInfo]:
        if not self.index_path.exists():
            return []
        with sqlite3.connect(self.index_path) as conn:
            cur = conn.execute(
                "SELECT hash, chosen_symbol, baseline_symbol, accepted_at "
                "FROM adoptions WHERE concept = ? ORDER BY accepted_at DESC LIMIT ?",
                (concept, limit),
            )
            rows = cur.fetchall()
        return [
            AdoptionInfo(
                adoption_hash=row[0],
                concept=concept,
                chosen_symbol=row[1],
                baseline_symbol=row[2],
                accepted_at=int(row[3]),
            )
            for row in rows
        ]

    def get_stat_cert_state(self) -> tuple[int, str] | None:
        if not self.index_path.exists():
            return None
        with sqlite3.connect(self.index_path) as conn:
            cur = conn.execute("SELECT round, alpha_spent FROM stat_cert_state WHERE state_id = 1")
            row = cur.fetchone()
        if row is None:
            return None
        return int(row[0]), str(row[1])


def _type_compat_score(target: str, candidate: str) -> int:
    if target == candidate:
        return 3
    target_parts = _split_top_level_arrows(target)
    cand_parts = _split_top_level_arrows(candidate)
    if not target_parts or not cand_parts:
        return 0
    target_ret = target_parts[-1]
    cand_ret = cand_parts[-1]
    if len(target_parts) == len(cand_parts) and target_ret == cand_ret:
        return 2
    if target_ret == cand_ret:
        return 1
    return 0


def _split_top_level_arrows(type_norm: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    i = 0
    while i < len(type_norm):
        ch = type_norm[i]
        if ch in "([":
            depth += 1
            buf.append(ch)
            i += 1
            continue
        if ch in ")]":
            depth = max(0, depth - 1)
            buf.append(ch)
            i += 1
            continue
        if depth == 0 and type_norm[i : i + 2] == "->":
            part = "".join(buf).strip()
            if part:
                parts.append(part)
            buf = []
            i += 2
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts
