"""Description length metric for ontology v2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from ..canon import canon_bytes, hash_json, sha256_prefixed
from ..ctime.trace import load_trace_jsonl
from .dsl import evaluate_ontology, _wrap_i32


@dataclass
class DlMetrics:
    dl_bits: int
    rent_bits: int
    model_bits: int
    data_bits: int
    action_names: list[str]
    context_count: int


def _ceil_log2(n: int) -> int:
    if n <= 1:
        return 0
    bits = 0
    value = 1
    while value < n:
        value <<= 1
        bits += 1
    return bits


def _u32_from_hash(value: str) -> int:
    if not isinstance(value, str):
        return 0
    hex_part = value.split(":", 1)[1] if ":" in value else value
    if len(hex_part) < 8:
        return 0
    try:
        return int(hex_part[:8], 16)
    except ValueError:
        return 0


def core_from_trace(event: dict[str, Any]) -> dict[str, Any]:
    obs_hash = event.get("obs_hash")
    post_obs_hash = event.get("post_obs_hash")
    family_id = event.get("family_id")
    return {
        "obs_hash": obs_hash,
        "post_obs_hash": post_obs_hash,
        "inst_hash": event.get("inst_hash"),
        "family_id": family_id,
        "epoch_id": event.get("epoch_id"),
        "obs_u32": _wrap_i32(_u32_from_hash(obs_hash)),
        "post_obs_u32": _wrap_i32(_u32_from_hash(post_obs_hash)),
        "family_u32": _wrap_i32(_u32_from_hash(family_id)),
        "t_step": int(event.get("t_step", 0)),
    }


def _context_hash(obj: dict[str, Any]) -> str:
    return hash_json(obj)


def _action_symbol(event: dict[str, Any]) -> str:
    action = event.get("action") if isinstance(event, dict) else None
    if isinstance(action, dict) and isinstance(action.get("name"), str):
        return action.get("name")
    return ""


def _collect_action_names(events: Iterable[dict[str, Any]]) -> list[str]:
    names = {name for name in (_action_symbol(e) for e in events) if name}
    return sorted(names)


def _dl_bits_for_events(
    events: list[dict[str, Any]],
    *,
    ontology_def: dict[str, Any] | None,
    rent_bits: int,
    include_rent: bool,
) -> DlMetrics:
    action_names = _collect_action_names(events)
    alphabet_size = len(action_names)
    if alphabet_size <= 0:
        alphabet_size = 1
    action_id_bits = _ceil_log2(alphabet_size)
    alt_bits = _ceil_log2(max(alphabet_size - 1, 1))

    context_counts: dict[str, dict[str, int]] = {}
    for event in events:
        z_core = core_from_trace(event)
        if ontology_def is None:
            ctx_obj = {"schema_version": 0, "ontology_id": None, "values": []}
        else:
            values = evaluate_ontology(ontology_def, z_core)
            ctx_obj = {
                "schema_version": 2,
                "ontology_id": ontology_def.get("ontology_id"),
                "values": values,
            }
        ctx = _context_hash(ctx_obj)
        bucket = context_counts.setdefault(ctx, {})
        action_name = _action_symbol(event)
        bucket[action_name] = bucket.get(action_name, 0) + 1

    model_bits = len(context_counts) * action_id_bits
    data_bits = 0
    for counts in context_counts.values():
        n_ctx = sum(counts.values())
        default_action = _default_action(counts)
        n_nondefault = n_ctx - counts.get(default_action, 0)
        data_bits += n_ctx + n_nondefault * alt_bits

    total_rent = rent_bits if include_rent else 0
    dl_bits = total_rent + model_bits + data_bits
    return DlMetrics(
        dl_bits=int(dl_bits),
        rent_bits=int(total_rent),
        model_bits=int(model_bits),
        data_bits=int(data_bits),
        action_names=action_names,
        context_count=len(context_counts),
    )


def _default_action(counts: dict[str, int]) -> str:
    if not counts:
        return ""
    best = None
    best_count = -1
    for name, count in counts.items():
        if count > best_count:
            best = name
            best_count = count
        elif count == best_count and best is not None and name < best:
            best = name
    return best or ""


def rent_bits_for_ontology(ontology_def: dict[str, Any], snapshot: dict[str, Any] | None) -> int:
    bits = len(canon_bytes(ontology_def)) * 8
    if snapshot is not None:
        bits += len(canon_bytes(snapshot)) * 8
    return int(bits)


def compute_dl_metrics(
    *,
    events: list[dict[str, Any]],
    ontology_def: dict[str, Any] | None,
    snapshot: dict[str, Any] | None = None,
    include_rent: bool = True,
) -> DlMetrics:
    rent_bits = 0
    if ontology_def is not None:
        rent_bits = rent_bits_for_ontology(ontology_def, snapshot)
    return _dl_bits_for_events(events, ontology_def=ontology_def, rent_bits=rent_bits, include_rent=include_rent)


def load_corpus_traces(trace_paths: list[str]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for path in trace_paths:
        events.extend(load_trace_jsonl(path))
    return events


def corpus_hash(window_epochs: list[int], trace_hashes: list[str]) -> str:
    payload = {"window_epochs": window_epochs, "trace_hashes": trace_hashes}
    return sha256_prefixed(canon_bytes(payload))
