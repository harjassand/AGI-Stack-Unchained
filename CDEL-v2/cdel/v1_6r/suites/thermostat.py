"""Pressure schedule update helper for v1.5r."""

from __future__ import annotations

from typing import Any


def update_pressure_schedule(
    schedule: dict[str, Any],
    *,
    worst_anchor: int,
    tau_high: int,
    tau_low: int,
    n_high: int,
    n_low: int,
) -> dict[str, Any]:
    _ = tau_high, tau_low, n_high, n_low
    payload = dict(schedule) if isinstance(schedule, dict) else {}
    payload.setdefault("schema", "pressure_schedule_v1")
    payload.setdefault("schema_version", 1)
    payload["p_t"] = int(payload.get("p_t", 0))
    history = payload.get("history")
    if not isinstance(history, list):
        history = []
    history.append({"worst_anchor": int(worst_anchor)})
    payload["history"] = history
    return payload
