"""Dev-only nuisance rate-scale classification helpers (v1.2)."""

from __future__ import annotations

from typing import Any

ACTION_CORR_HIGH = 0.6
NOISE_HIGH = 0.6


def _signature(anomaly_buffer: dict[str, Any], regime_id: str = "nuisance_k2_00") -> dict[str, Any] | None:
    signatures = anomaly_buffer.get("failure_signatures") or {}
    if not isinstance(signatures, dict) or not signatures:
        return None
    if regime_id in signatures and isinstance(signatures[regime_id], dict):
        return signatures[regime_id]
    first_key = sorted(signatures.keys())[0]
    sig = signatures.get(first_key)
    return sig if isinstance(sig, dict) else None


def classify_nuisance_rate_scale(
    *,
    anomaly_buffer: dict[str, Any],
    sequence_oracle: dict[str, Any] | None = None,
    memoryless_oracle: dict[str, Any] | None = None,
    depth2_oracle: dict[str, Any] | None = None,
    regime_id: str = "nuisance_k2_00",
) -> dict[str, Any]:
    sig = _signature(anomaly_buffer, regime_id=regime_id)
    action_corr = 0.0
    noise_score = 0.0
    if isinstance(sig, dict):
        try:
            action_corr = float(sig.get("action_correlation_score", 0.0))
        except (TypeError, ValueError):
            action_corr = 0.0
        try:
            noise_score = float(sig.get("noise_score", 0.0))
        except (TypeError, ValueError):
            noise_score = 0.0

    label = "UNKNOWN"
    rule = "diagnostics_insufficient"
    needs_retry = False
    unsolvable = False

    if isinstance(sequence_oracle, dict) and sequence_oracle.get("found") is False:
        horizon = int(sequence_oracle.get("horizon", 0))
        if horizon < 64:
            needs_retry = True
            rule = "sequence_oracle_failed_retry_h64"
        else:
            unsolvable = True
            rule = "sequence_oracle_failed_h64"
        return {
            "label": "UNKNOWN",
            "rule": rule,
            "action_correlation_score": action_corr,
            "noise_score": noise_score,
            "needs_sequence_retry": needs_retry,
            "unsolvable": unsolvable,
            "sequence_oracle": sequence_oracle,
            "memoryless_oracle": memoryless_oracle,
            "depth2_oracle": depth2_oracle,
        }

    if isinstance(memoryless_oracle, dict) and memoryless_oracle.get("found") is True:
        if action_corr >= ACTION_CORR_HIGH:
            label = "TIME_SCALE"
            rule = "memoryless_high_action_corr"
        elif noise_score >= NOISE_HIGH:
            label = "OBS_NOISE"
            rule = "memoryless_high_noise"
        else:
            label = "UNKNOWN"
            rule = "memoryless_low_signal"
    elif isinstance(sequence_oracle, dict) and sequence_oracle.get("found") is True:
        if isinstance(memoryless_oracle, dict) and memoryless_oracle.get("found") is False:
            if isinstance(depth2_oracle, dict) and depth2_oracle.get("found") is True:
                label = "MEMORY_REQUIRED"
                rule = "depth2_found"
            else:
                label = "MEMORY_REQUIRED"
                rule = "depth2_missing_or_failed"

    return {
        "label": label,
        "rule": rule,
        "action_correlation_score": action_corr,
        "noise_score": noise_score,
        "needs_sequence_retry": needs_retry,
        "unsolvable": unsolvable,
        "sequence_oracle": sequence_oracle,
        "memoryless_oracle": memoryless_oracle,
        "depth2_oracle": depth2_oracle,
    }
