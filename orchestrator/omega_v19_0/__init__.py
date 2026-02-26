"""Omega v19.0 orchestrator adapters."""

from __future__ import annotations

from typing import Any


def run_promotion(*args: Any, **kwargs: Any) -> Any:
    from .promoter_v1 import run_promotion as _run_promotion

    return _run_promotion(*args, **kwargs)


def run_subverifier(*args: Any, **kwargs: Any) -> Any:
    from .promoter_v1 import run_subverifier as _run_subverifier

    return _run_subverifier(*args, **kwargs)


__all__ = ["run_promotion", "run_subverifier"]
