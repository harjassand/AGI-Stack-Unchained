"""Deterministic context pack builder for LLM proposers."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from blake3 import blake3

from orchestrator.concept_registry import ConceptIndex
from orchestrator.spec_synthesis import synthesize_specs

@dataclass(frozen=True)
class ContextPackLimits:
    max_new_symbols: int
    max_ast_nodes: int
    max_ast_depth: int
    allow_primitives: list[str] | None = None
    max_definition_chars: int = 2000
    max_concepts: int = 5
    max_spec_items: int = 5


def build_context_pack_v1(
    *,
    root_dir: Path,
    config_path: Path,
    concept: str,
    baseline_symbol: str,
    oracle_symbol: str,
    context_symbols: list[str],
    counterexamples: list[dict],
    rng_seed: int,
    limits: ContextPackLimits,
    context_concepts: list[str] | None = None,
) -> dict[str, Any]:
    _ = config_path
    index_path = root_dir / "index" / "index.sqlite"
    conn = sqlite3.connect(str(index_path)) if index_path.exists() else None
    try:
        symbols = _ordered_symbols(baseline_symbol, oracle_symbol, context_symbols)
        summaries = [
            _symbol_summary(conn, symbol, role=_symbol_role(symbol, baseline_symbol, oracle_symbol), limits=limits)
            for symbol in symbols
        ]
        concepts = _concept_summaries(
            root_dir=root_dir,
            concept=concept,
            context_concepts=context_concepts,
            max_concepts=limits.max_concepts,
        )
        spec_hints = synthesize_specs(counterexamples, max_items=limits.max_spec_items)
    finally:
        if conn is not None:
            conn.close()

    payload = {
        "version": "context-pack-v1",
        "concept": concept,
        "baseline_symbol": baseline_symbol,
        "oracle_symbol": oracle_symbol,
        "rng_seed": rng_seed,
        "limits": {
            "max_new_symbols": limits.max_new_symbols,
            "max_ast_nodes": limits.max_ast_nodes,
            "max_ast_depth": limits.max_ast_depth,
            "allow_primitives": sorted(limits.allow_primitives) if limits.allow_primitives else None,
            "max_definition_chars": limits.max_definition_chars,
            "max_concepts": limits.max_concepts,
            "max_spec_items": limits.max_spec_items,
        },
        "symbols": summaries,
        "concepts": concepts,
        "retrieval": {
            "symbols": symbols,
            "concepts": [item["concept_id"] for item in concepts],
            "plans": [],
        },
        "spec_hints": spec_hints,
        "counterexamples": _stable_sort(counterexamples),
    }
    return payload


def _symbol_role(symbol: str, baseline: str, oracle: str) -> str:
    if symbol == baseline:
        return "baseline"
    if symbol == oracle:
        return "oracle"
    return "context"


def _ordered_symbols(baseline: str, oracle: str, context: Iterable[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for name in [baseline, oracle, *context]:
        if not name or name in seen:
            continue
        ordered.append(name)
        seen.add(name)
    return ordered


def _symbol_summary(
    conn: sqlite3.Connection | None,
    symbol: str,
    *,
    role: str,
    limits: ContextPackLimits,
) -> dict[str, Any]:
    module_hash, type_norm = _symbol_info(conn, symbol)
    deps = _symbol_deps(conn, symbol)
    definition = _load_definition(conn, module_hash, symbol)
    summary = {
        "name": symbol,
        "role": role,
        "type_norm": type_norm,
        "deps": deps,
    }
    if definition is None:
        summary.update(
            {
                "definition_hash": None,
                "definition_preview": "",
                "truncated": False,
                "original_len": 0,
            }
        )
        return summary

    canonical = _canonical_json(definition)
    def_hash = blake3(canonical.encode("utf-8")).hexdigest()
    if len(canonical) > limits.max_definition_chars:
        summary.update(
            {
                "definition_hash": def_hash,
                "definition_preview": canonical[: limits.max_definition_chars],
                "truncated": True,
                "original_len": len(canonical),
            }
        )
    else:
        summary.update(
            {
                "definition_hash": def_hash,
                "definition_json": definition,
                "truncated": False,
                "original_len": len(canonical),
            }
        )
    return summary


def _symbol_info(conn: sqlite3.Connection | None, symbol: str) -> tuple[str | None, str]:
    if conn is None:
        return None, ""
    cur = conn.execute("SELECT module_hash, type_norm FROM symbols WHERE symbol = ?", (symbol,))
    row = cur.fetchone()
    if row is None:
        return None, ""
    return str(row[0]), str(row[1])


def _symbol_deps(conn: sqlite3.Connection | None, symbol: str) -> list[str]:
    if conn is None:
        return []
    cur = conn.execute("SELECT dep_symbol FROM sym_deps WHERE symbol = ?", (symbol,))
    rows = cur.fetchall()
    return [row[0] for row in rows]


def _load_definition(
    conn: sqlite3.Connection | None,
    module_hash: str | None,
    symbol: str,
) -> dict[str, Any] | None:
    if conn is None or module_hash is None:
        return None
    cur = conn.execute("SELECT bytes FROM modules WHERE hash = ?", (module_hash,))
    row = cur.fetchone()
    if row is None or row[0] is None:
        return None
    raw = row[0]
    if isinstance(raw, memoryview):
        raw = raw.tobytes()
    if isinstance(raw, bytes):
        text = raw.decode("utf-8")
    else:
        text = str(raw)
    try:
        module_obj = json.loads(text)
    except json.JSONDecodeError:
        return None
    payload = module_obj.get("payload")
    if not isinstance(payload, dict):
        if isinstance(module_obj, dict) and "definitions" in module_obj:
            payload = module_obj
        else:
            return None
    defs = payload.get("definitions")
    if not isinstance(defs, list):
        return None
    for defn in defs:
        if isinstance(defn, dict) and defn.get("name") == symbol:
            return defn
    return None


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _stable_sort(items: Iterable[dict]) -> list[dict]:
    rows = list(items)
    rows.sort(key=lambda item: _canonical_json(item))
    return rows


def _concept_summaries(
    *,
    root_dir: Path,
    concept: str,
    context_concepts: list[str] | None,
    max_concepts: int,
) -> list[dict[str, Any]]:
    registry_path = _resolve_registry_path(root_dir)
    if registry_path is None or not registry_path.exists():
        return []
    index = ConceptIndex.from_path(registry_path)
    entries = index.entries
    if not entries:
        return []
    entry_map = {entry.concept_id: entry for entry in entries}
    if context_concepts is None:
        query_text = " ".join([concept])
        concept_ids = [entry.concept_id for entry in index.top_k(query_text, limit=max_concepts)]
    else:
        concept_ids = list(context_concepts)
    ordered_ids = _ordered_concepts(concept, concept_ids, entry_map)
    summaries: list[dict[str, Any]] = []
    for concept_id in ordered_ids[:max_concepts]:
        entry = entry_map.get(concept_id)
        if entry is None:
            continue
        summaries.append(
            {
                "concept_id": entry.concept_id,
                "description": entry.description,
                "examples": entry.examples,
                "tags": entry.tags,
                "dependencies": entry.dependencies,
                "stats": entry.stats,
                "hash": entry.content_hash,
            }
        )
    return summaries


def _ordered_concepts(
    primary: str,
    candidates: Iterable[str],
    registry: dict[str, Any],
) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for name in [primary, *candidates]:
        if not name or name in seen or name not in registry:
            continue
        ordered.append(name)
        seen.add(name)
    return ordered


def _resolve_registry_path(root_dir: Path) -> Path | None:
    candidate = root_dir / "concepts" / "registry.jsonl"
    if candidate.exists():
        return candidate
    repo_root = Path(__file__).resolve().parents[1]
    fallback = repo_root / "concepts" / "registry.jsonl"
    if fallback.exists():
        return fallback
    return None
