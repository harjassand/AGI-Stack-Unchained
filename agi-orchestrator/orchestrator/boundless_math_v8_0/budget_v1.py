"""Budget tracking for boundless math attempts (v8.0)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MathBudget:
    attempts_today: int
    attempts_per_tick_max: int
    daily_attempt_budget: int

    def can_attempt(self, attempts_this_tick: int) -> bool:
        if attempts_this_tick >= self.attempts_per_tick_max:
            return False
        if self.attempts_today >= self.daily_attempt_budget:
            return False
        return True

    def record_attempt(self) -> None:
        self.attempts_today += 1


__all__ = ["MathBudget"]
