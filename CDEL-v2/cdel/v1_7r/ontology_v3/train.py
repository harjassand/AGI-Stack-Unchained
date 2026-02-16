"""Deterministic training for ontology v3 context kernel."""

from __future__ import annotations

from typing import Any

from ..canon import CanonError
from ..hashutil import compute_self_hash
from .dl_metric import compute_dl_metrics


def _concept_ids(ontology_def: dict[str, Any]) -> list[str]:
    concepts = ontology_def.get("concepts")
    if not isinstance(concepts, list):
        return []
    ids: list[str] = []
    for concept in concepts:
        if isinstance(concept, dict) and isinstance(concept.get("concept_id"), str):
            ids.append(concept.get("concept_id"))
    return ids


def build_snapshot(
    *,
    ontology_def: dict[str, Any],
    epoch_id: str,
    window_epochs: list[int],
    corpus_hash: str,
    selected_concept_ids: list[str],
    meta: dict[str, str],
) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "schema": "ontology_snapshot_v3",
        "schema_version": 3,
        "snapshot_id": "__SELF__",
        "epoch_id": epoch_id,
        "ontology_id": ontology_def.get("ontology_id"),
        "trained_on": {"window_epochs": window_epochs, "corpus_hash": corpus_hash},
        "context_kernel_state": {
            "schema": "onto_context_kernel_state_v1",
            "schema_version": 1,
            "selected_concept_ids": list(selected_concept_ids),
            "arity": len(selected_concept_ids),
        },
        "x-meta": meta,
    }
    snapshot["snapshot_id"] = compute_self_hash(snapshot, "snapshot_id")
    return snapshot


def train_snapshot(
    *,
    ontology_def: dict[str, Any],
    events: list[dict[str, Any]],
    epoch_id: str,
    window_epochs: list[int],
    corpus_hash: str,
    meta: dict[str, str],
) -> dict[str, Any]:
    context_kernel = ontology_def.get("context_kernel")
    training = ontology_def.get("training")
    if not isinstance(context_kernel, dict) or not isinstance(training, dict):
        raise CanonError("ontology_def missing training specs")
    max_arity = int(context_kernel.get("max_arity", 0))
    stop_gain = int(training.get("stop_if_gain_bits_lt", 0))

    concept_ids = _concept_ids(ontology_def)
    selected: list[str] = []

    base_snapshot = build_snapshot(
        ontology_def=ontology_def,
        epoch_id=epoch_id,
        window_epochs=window_epochs,
        corpus_hash=corpus_hash,
        selected_concept_ids=selected,
        meta=meta,
    )
    base_dl = compute_dl_metrics(events=events, ontology_def=ontology_def, snapshot=base_snapshot).dl_bits

    for _ in range(max_arity):
        best_gain = None
        best_id = None
        best_dl = None
        for cid in sorted(concept_ids):
            if cid in selected:
                continue
            candidate_selected = selected + [cid]
            candidate_snapshot = build_snapshot(
                ontology_def=ontology_def,
                epoch_id=epoch_id,
                window_epochs=window_epochs,
                corpus_hash=corpus_hash,
                selected_concept_ids=candidate_selected,
                meta=meta,
            )
            candidate_dl = compute_dl_metrics(events=events, ontology_def=ontology_def, snapshot=candidate_snapshot).dl_bits
            gain = base_dl - candidate_dl
            if best_gain is None or gain > best_gain or (gain == best_gain and best_id is not None and cid < best_id):
                best_gain = gain
                best_id = cid
                best_dl = candidate_dl
        if best_gain is None or best_id is None:
            break
        if best_gain < stop_gain:
            break
        selected.append(best_id)
        base_dl = int(best_dl) if best_dl is not None else base_dl

    return build_snapshot(
        ontology_def=ontology_def,
        epoch_id=epoch_id,
        window_epochs=window_epochs,
        corpus_hash=corpus_hash,
        selected_concept_ids=selected,
        meta=meta,
    )
