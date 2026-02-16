"""Deterministic tick engine for daemon v6.0."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class BudgetCounters:
    ticks_this_boot: int = 0
    work_units_today: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "ticks_this_boot": int(self.ticks_this_boot),
            "work_units_today": int(self.work_units_today),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "BudgetCounters":
        payload = payload or {}
        return cls(
            ticks_this_boot=int(payload.get("ticks_this_boot", 0)),
            work_units_today=int(payload.get("work_units_today", 0)),
        )


class TickEngine:
    def __init__(self, *, current_tick: int, budgets: dict[str, Any], counters: BudgetCounters) -> None:
        self.current_tick = int(current_tick)
        self.budgets = budgets
        self.counters = counters

    def can_advance(self) -> bool:
        max_ticks = int(self.budgets.get("max_ticks_per_boot", 1))
        max_work = int(self.budgets.get("max_work_units_per_day", 1))
        if self.counters.ticks_this_boot >= max_ticks:
            return False
        if self.counters.work_units_today >= max_work:
            return False
        return True

    def next_tick(self) -> int:
        self.counters.ticks_this_boot += 1
        self.current_tick += 1
        return self.current_tick

    def record_work_units(self, units: int) -> None:
        self.counters.work_units_today += int(units)


__all__ = ["BudgetCounters", "TickEngine"]
