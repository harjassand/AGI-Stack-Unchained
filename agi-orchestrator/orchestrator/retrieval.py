"""Deterministic retrieval for candidate context."""

from __future__ import annotations

from pathlib import Path

from orchestrator.concept_registry import ConceptIndex
from orchestrator.ledger_view import LedgerView
from orchestrator.types import ContextBundle


def retrieve_context(
    *,
    ledger: LedgerView,
    bundle: ContextBundle,
    limit: int = 10,
    failure_symbols: list[str] | None = None,
) -> list[str]:
    symbols: list[str] = []

    def add(name: str) -> None:
        if name and name not in symbols:
            symbols.append(name)

    add(bundle.baseline_symbol)
    add(bundle.oracle_symbol)
    for name in failure_symbols or []:
        add(name)

    concept_symbols = ledger.get_symbols_for_concept(bundle.concept, limit=limit)
    for info in concept_symbols:
        add(info.name)

    for name in ledger.get_symbols_by_type(bundle.type_norm, limit=limit):
        add(name)

    for name in ledger.get_type_compatible_symbols(bundle.type_norm, limit=limit):
        add(name)

    return symbols


def retrieve_concepts(*, registry_path: Path, query_text: str, limit: int = 5) -> list[str]:
    if not registry_path.exists():
        return []
    index = ConceptIndex.from_path(registry_path)
    return [entry.concept_id for entry in index.top_k(query_text, limit=limit)]
