"""RSI Omega daemon v18.0 package."""

from __future__ import annotations

from typing import Any


def verify(*args: Any, **kwargs: Any) -> Any:
    """Lazy-load replay verifier to avoid package import cycles at test collection."""
    from .verify_rsi_omega_daemon_v1 import verify as _verify

    return _verify(*args, **kwargs)


__all__ = ["verify"]
