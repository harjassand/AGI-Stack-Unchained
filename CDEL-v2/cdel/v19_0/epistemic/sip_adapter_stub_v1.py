"""Disabled SIP->ECP adapter stub for deferred milestone."""

from __future__ import annotations

import os

from ..common_v1 import fail


def ensure_disabled() -> None:
    raw = str(os.environ.get("OMEGA_ECP_ENABLE_SIP_ADAPTER", "0")).strip().lower()
    if raw not in {"", "0", "false", "off", "no"}:
        fail("SIP_ADAPTER_DISABLED")


__all__ = ["ensure_disabled"]
