"""Clock helpers (excluded from decision hashing)."""

from __future__ import annotations

import time


def sleep_seconds(value: float) -> None:
    time.sleep(max(0.0, float(value)))


__all__ = ["sleep_seconds"]
