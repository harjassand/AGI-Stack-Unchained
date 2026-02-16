"""Description length metric for ontology v3."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ..canon import canon_bytes, sha256_prefixed
from ..demon.trace import load_trace_jsonl
from .bucket import apply_bucketer
from .context_kernel import build_ctx_key, build_null_ctx_key, ctx_hash
from .dsl import eval_expr, _wrap_i32


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
        "obs_u32": _wrap_i32(_u32_from_hash(obs_hash)),
        "post_obs_u32": _wrap_i32(_u32_from_hash(post_obs_hash)),
        "family_u32": _wrap_i32(_u32_from_hash(family_id)),
        "t_step": int(event.get("t_step", 0)),
    }


def _action_symbol(event: dict[str, Any]) -> str:
    action = event.get("action") if isinstance(event, dict) else None
    if isinstance(action, dict) and isinstance(action.get("name"), str):
        return action.get("name")
    return ""


def _collect_action_names(events: Iterable[dict[str, Any]]) -> list[str]:
    names = {name for name in (_action_symbol(e) for e in events) if name}
    return sorted(names)


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


def _selected_concepts(snapshot: dict[str, Any]) -> list[str]:
    state = snapshot.get("context_kernel_state") if isinstance(snapshot, dict) else None
    if not isinstance(state, dict):
        return []
    ids = state.get("selected_concept_ids")
    if not isinstance(ids, list):
        return []
    return [str(cid) for cid in ids]


def _concept_by_id(ontology_def: dict[str, Any]) -> dict[str, dict[str, Any]]:
    concepts = ontology_def.get("concepts")
    if not isinstance(concepts, list):
        return {}
    mapping: dict[str, dict[str, Any]] = {}
    for concept in concepts:
        if isinstance(concept, dict):
            cid = concept.get("concept_id")
            if isinstance(cid, str):
                mapping[cid] = concept
    return mapping


def context_values_for_event(event: dict[str, Any], ontology_def: dict[str, Any], snapshot: dict[str, Any]) -> list[int]:
    selected_ids = _selected_concepts(snapshot)
    if not selected_ids:
        return []
    concepts = _concept_by_id(ontology_def)
    z_core = core_from_trace(event)
    values: list[int] = []
    for cid in selected_ids:
        concept = concepts.get(cid)
        if not isinstance(concept, dict):
            raise ValueError("snapshot references unknown concept_id")
        output_type = concept.get("output_type")
        expr = concept.get("expr")
        val = eval_expr(expr, z_core)
        bucketer = concept.get("bucketer")
        values.append(apply_bucketer(val, bucketer, output_type))
    return values


def context_hash_for_event(event: dict[str, Any], ontology_def: dict[str, Any], snapshot: dict[str, Any]) -> str:
    values = context_values_for_event(event, ontology_def, snapshot)
    ctx = build_ctx_key(ontology_def.get("ontology_id"), snapshot.get("snapshot_id"), values)
    return ctx_hash(ctx)


def rent_bits_for_ontology(ontology_def: dict[str, Any], snapshot: dict[str, Any]) -> int:
    bits = len(canon_bytes(ontology_def)) * 8
    bits += len(canon_bytes(snapshot)) * 8
    return int(bits)


def _dl_bits_for_events(
    events: list[dict[str, Any]],
    *,
    ontology_def: dict[str, Any] | None,
    snapshot: dict[str, Any] | None,
    include_rent: bool,
) -> DlMetrics:
    action_names = _collect_action_names(events)
    alphabet_size = len(action_names)
    if alphabet_size <= 0:
        alphabet_size = 1
    action_id_bits = _ceil_log2(alphabet_size)
    alt_bits = _ceil_log2(max(alphabet_size - 1, 1))

    context_counts: dict[str, dict[str, int]] = {}
    if ontology_def is None or snapshot is None:
        ctx_key = build_null_ctx_key()
        ctx_id = ctx_hash(ctx_key)
        for event in events:
            bucket = context_counts.setdefault(ctx_id, {})
            action_name = _action_symbol(event)
            bucket[action_name] = bucket.get(action_name, 0) + 1
    else:
        for event in events:
            ctx_id = context_hash_for_event(event, ontology_def, snapshot)
            bucket = context_counts.setdefault(ctx_id, {})
            action_name = _action_symbol(event)
            bucket[action_name] = bucket.get(action_name, 0) + 1

    model_bits = len(context_counts) * action_id_bits
    data_bits = 0
    for counts in context_counts.values():
        n_ctx = sum(counts.values())
        default_action = _default_action(counts)
        n_nondefault = n_ctx - counts.get(default_action, 0)
        data_bits += n_ctx + n_nondefault * alt_bits

    total_rent = 0
    if include_rent and ontology_def is not None and snapshot is not None:
        total_rent = rent_bits_for_ontology(ontology_def, snapshot)

    dl_bits = total_rent + model_bits + data_bits
    return DlMetrics(
        dl_bits=int(dl_bits),
        rent_bits=int(total_rent),
        model_bits=int(model_bits),
        data_bits=int(data_bits),
        action_names=action_names,
        context_count=len(context_counts),
    )


def compute_dl_metrics(
    *,
    events: list[dict[str, Any]],
    ontology_def: dict[str, Any] | None,
    snapshot: dict[str, Any] | None,
    include_rent: bool = True,
) -> DlMetrics:
    return _dl_bits_for_events(events, ontology_def=ontology_def, snapshot=snapshot, include_rent=include_rent)


def load_corpus_traces(trace_paths: list[str]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for path in trace_paths:
        events.extend(load_trace_jsonl(path))
    return events


def corpus_hash(window_epochs: list[int], trace_hashes: list[str]) -> str:
    payload = {"window_epochs": window_epochs, "trace_hashes": trace_hashes}
    return sha256_prefixed(canon_bytes(payload))


def trace_hash(path: Path) -> str:
    return sha256_prefixed(path.read_bytes())
