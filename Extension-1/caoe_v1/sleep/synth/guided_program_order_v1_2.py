"""Guided program ordering for CAOE v1.2 (dev-only heuristics)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Iterable

base_dir = Path(__file__).resolve().parents[2]
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))

from api_v1 import canonical_json_bytes  # noqa: E402


def _signature_from_buffer(anomaly_buffer: dict[str, Any]) -> dict[str, Any] | None:
    signatures = anomaly_buffer.get("failure_signatures") or {}
    if not isinstance(signatures, dict) or not signatures:
        return None
    if "nuisance_k2_00" in signatures and isinstance(signatures["nuisance_k2_00"], dict):
        return signatures["nuisance_k2_00"]
    first_key = sorted(signatures.keys())[0]
    sig = signatures.get(first_key)
    return sig if isinstance(sig, dict) else None


def _controllable_indices(signature: dict[str, Any]) -> set[int]:
    action_map = signature.get("action_conditioned_effect_map") or {}
    indices: set[int] = set()
    if isinstance(action_map, dict):
        for entry in action_map.values():
            if not isinstance(entry, dict):
                continue
            for idx in entry.get("changed_indices") or []:
                if isinstance(idx, int):
                    indices.add(idx)
    return indices


def _flip_rates(signature: dict[str, Any]) -> dict[int, float]:
    rates: dict[int, float] = {}
    flip_summary = signature.get("flip_rate_summary") or {}
    per_rate = flip_summary.get("per_index_flip_rate") if isinstance(flip_summary, dict) else None
    if isinstance(per_rate, dict):
        for key, val in per_rate.items():
            try:
                idx = int(key)
                rate = float(val)
            except (TypeError, ValueError):
                continue
            rates[idx] = rate
    return rates


def _classification_hint(anomaly_buffer: dict[str, Any], signature: dict[str, Any]) -> str | None:
    dev_class = anomaly_buffer.get("dev_classification")
    if isinstance(dev_class, dict):
        label = dev_class.get("label")
        if isinstance(label, str):
            return label
    try:
        noise = float(signature.get("noise_score", 0.0))
        action_corr = float(signature.get("action_correlation_score", 0.0))
    except (TypeError, ValueError):
        return None
    if noise >= 0.6:
        return "OBS_NOISE"
    if action_corr >= 0.6:
        return "TIME_SCALE"
    return None


def _indices_used(program: dict[str, Any]) -> tuple[set[int], bool, int]:
    ops = program.get("ops") or []
    used: set[int] = set()
    uses_history = False
    for op in ops:
        if not isinstance(op, dict):
            continue
        args = op.get("args") or []
        if not args:
            continue
        for arg in args:
            if isinstance(arg, str) and arg in {"o_t_minus_1", "o_t_minus_2"}:
                uses_history = True
        op_name = op.get("op")
        if op_name == "SELECT_BIT":
            if len(args) >= 2 and isinstance(args[0], str) and isinstance(args[1], int):
                used.add(int(args[1]))
        elif op_name == "SLICE":
            if len(args) >= 3 and isinstance(args[0], str) and isinstance(args[1], int) and isinstance(args[2], int):
                start = int(args[1])
                end = int(args[2])
                for idx in range(start, max(start, end)):
                    used.add(idx)
    op_count = len(ops)
    return used, uses_history, op_count


def _program_bytes(entry: dict[str, Any]) -> bytes:
    data = entry.get("bytes")
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    program = entry.get("program") or {}
    return canonical_json_bytes(program)


def order_programs(
    entries: Iterable[dict[str, Any]],
    *,
    anomaly_buffer: dict[str, Any],
) -> list[dict[str, Any]]:
    signature = _signature_from_buffer(anomaly_buffer)
    if signature is None:
        return list(entries)

    controllable = _controllable_indices(signature)
    flip_rates = _flip_rates(signature)
    try:
        action_corr = float(signature.get("action_correlation_score", 0.0))
    except (TypeError, ValueError):
        action_corr = 0.0
    try:
        noise_score = float(signature.get("noise_score", 0.0))
    except (TypeError, ValueError):
        noise_score = 0.0
    classification = _classification_hint(anomaly_buffer, signature)

    scored: list[tuple[int, bytes, dict[str, Any]]] = []
    for entry in entries:
        program = entry.get("program") or {}
        indices, uses_history, op_count = _indices_used(program)
        overlap = indices.intersection(controllable)
        action_boost = max(1, int(5 * action_corr))
        score = action_boost * len(overlap)
        noise_penalty = sum(flip_rates.get(idx, 0.0) for idx in indices)
        score -= int(5 * noise_score * noise_penalty)
        if classification in {"OBS_NOISE", "MEMORY_REQUIRED"} and uses_history:
            score += 3
        # Late length penalty.
        score -= op_count // 10
        scored.append((int(score), _program_bytes(entry), entry))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [entry for _score, _bytes, entry in scored]
