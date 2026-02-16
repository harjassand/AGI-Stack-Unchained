"""Candidate ranking helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from cdel.kernel.cost import count_term_nodes
from cdel.kernel.parse import parse_definition

from orchestrator.types import Candidate


@dataclass(frozen=True)
class RankedCandidate:
    candidate: Candidate
    diff_sum: int
    ast_nodes: int
    new_symbols: int
    attempt_idx: int
    candidate_path: Path


def candidate_payload_hash(payload: dict) -> str:
    blob = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def count_candidate_ast_nodes(payload: dict) -> int:
    total = 0
    for defn in payload.get("definitions", []):
        parsed = parse_definition(defn)
        total += count_term_nodes(parsed.body)
    return total


def rank_candidates(entries: list[RankedCandidate]) -> list[RankedCandidate]:
    return sorted(entries, key=lambda item: (-item.diff_sum, item.ast_nodes, item.new_symbols))
