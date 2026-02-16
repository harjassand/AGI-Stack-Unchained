"""Capability enforcement for superego requests (v7.0)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class CapabilityViolation(RuntimeError):
    pass


def enforce_capabilities(request: dict[str, Any], *, agi_root: Path, daemon_root: Path) -> None:
    caps = set(request.get("capabilities") or [])
    targets = request.get("target_paths") or []

    if "NETWORK_ANY" in caps:
        raise CapabilityViolation("DAEMON_FORBIDDEN_CAPABILITY")

    allowed_prefixes: list[str] = []
    if "FS_WRITE_RUNS_NEW" in caps:
        allowed_prefixes.append(str(agi_root / "runs"))
    if "FS_WRITE_DAEMON_STATE" in caps:
        allowed_prefixes.append(str(daemon_root / "state"))

    if not allowed_prefixes:
        allowed_prefixes.append(str(agi_root))

    for target in targets:
        if not isinstance(target, str):
            raise CapabilityViolation("DAEMON_FORBIDDEN_CAPABILITY")
        if not any(target.startswith(prefix) for prefix in allowed_prefixes):
            raise CapabilityViolation("DAEMON_FORBIDDEN_CAPABILITY")


__all__ = ["CapabilityViolation", "enforce_capabilities"]
