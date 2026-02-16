"""Efficiency gating helpers for v2.1 (re-exported from v2.0)."""

from __future__ import annotations

from ..v2_0.efficiency import (  # noqa: F401
    efficiency_gate,
    rho_pair,
    scalar_gate,
    vector_dominance,
    work_cost,
)

__all__ = [
    "efficiency_gate",
    "rho_pair",
    "scalar_gate",
    "vector_dominance",
    "work_cost",
]
