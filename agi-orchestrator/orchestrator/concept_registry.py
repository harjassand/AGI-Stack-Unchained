"""Concept registry loading and deterministic retrieval."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from blake3 import blake3

from orchestrator.embedding import EMBED_DIM, dot, embed_text


@dataclass(frozen=True)
class ConceptEntry:
    concept_id: str
    description: str
    examples: list[dict[str, Any]]
    tags: list[str]
    dependencies: list[str]
    stats: dict[str, int]
    content_hash: str


@dataclass(frozen=True)
class ConceptIndex:
    entries: list[ConceptEntry]
    embeddings: list[list[int]]
    dim: int = EMBED_DIM

    @classmethod
    def from_path(cls, path: Path) -> ConceptIndex:
        entries = load_concept_registry(path)
        embeddings = [embed_text(_concept_text(entry), dim=EMBED_DIM) for entry in entries]
        return cls(entries=entries, embeddings=embeddings, dim=EMBED_DIM)

    def top_k(self, query_text: str, limit: int = 5) -> list[ConceptEntry]:
        query_vec = embed_text(query_text, dim=self.dim)
        scored: list[tuple[int, str, ConceptEntry]] = []
        for entry, vec in zip(self.entries, self.embeddings):
            score = dot(query_vec, vec)
            scored.append((score, entry.concept_id, entry))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [entry for _, _, entry in scored[:limit]]


def load_concept_registry(path: Path) -> list[ConceptEntry]:
    if not path.exists():
        return []
    entries: list[ConceptEntry] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        normalized = _normalize_entry(raw)
        expected_hash = raw.get("hash")
        if not isinstance(expected_hash, str):
            raise ValueError("concept entry missing hash")
        computed_hash = compute_concept_hash(normalized)
        if computed_hash != expected_hash:
            raise ValueError(f"concept hash mismatch for {normalized.get('concept_id')}")
        entry = ConceptEntry(
            concept_id=str(normalized["concept_id"]),
            description=str(normalized["description"]),
            examples=list(normalized.get("examples", [])),
            tags=list(normalized.get("tags", [])),
            dependencies=list(normalized.get("dependencies", [])),
            stats=dict(normalized.get("stats", {})),
            content_hash=computed_hash,
        )
        entries.append(entry)
    entries.sort(key=lambda item: item.concept_id)
    return entries


def compute_concept_hash(entry: dict[str, Any]) -> str:
    canonical = _canonical_json(entry)
    return blake3(canonical.encode("utf-8")).hexdigest()


def _normalize_entry(raw: dict[str, Any]) -> dict[str, Any]:
    concept_id = str(raw.get("concept_id", "")).strip()
    description = str(raw.get("description", "")).strip()
    examples = raw.get("examples") or []
    if not isinstance(examples, list):
        raise ValueError("examples must be a list")
    tags = _sorted_unique(raw.get("tags") or [])
    dependencies = _sorted_unique(raw.get("dependencies") or [])
    stats = raw.get("stats") or {}
    if not isinstance(stats, dict):
        raise ValueError("stats must be a dict")
    normalized = {
        "concept_id": concept_id,
        "description": description,
        "examples": examples,
        "tags": tags,
        "dependencies": dependencies,
        "stats": {str(k): int(v) for k, v in sorted(stats.items())},
    }
    return normalized


def _concept_text(entry: ConceptEntry) -> str:
    parts: list[str] = [entry.concept_id, entry.description]
    for example in entry.examples:
        parts.append(_canonical_json(example))
    parts.extend(entry.tags)
    parts.extend(entry.dependencies)
    return " ".join(part for part in parts if part)


def _sorted_unique(items: Iterable[Any]) -> list[str]:
    return sorted({str(item) for item in items if str(item)})


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
