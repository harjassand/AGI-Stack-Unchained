"""Reward computation (v1)."""

from __future__ import annotations

from typing import Dict


def clamp(val: int, lo: int, hi: int) -> int:
    if val < lo:
        return lo
    if val > hi:
        return hi
    return val


def compute_reward(m_bp: int, m0_bp: int, costs: Dict[str, int], cfg: Dict[str, int]) -> int:
    A = int(cfg.get("A", 1))
    B1 = int(cfg.get("B1", 0))
    B2 = int(cfg.get("B2", 0))
    R = int(cfg.get("R", 1000000))
    patch_bytes = int(costs.get("patch_bytes", 0))
    test_runs = int(costs.get("test_runs", 0))
    raw = (int(m_bp) - int(m0_bp)) * A - patch_bytes * B1 - test_runs * B2
    return clamp(raw, -R, R)


__all__ = ["compute_reward", "clamp"]
