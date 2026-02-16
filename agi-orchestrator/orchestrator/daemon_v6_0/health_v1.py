"""Health report writer for daemon v6.0."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .io_atomic_v1 import atomic_write_json


def write_health_report(
    path: Path,
    *,
    daemon_id: str,
    icore_id: str,
    meta_hash: str,
    tick: int,
    boot_count: int,
    ledger_head_hash: str,
    status: str,
    paused_reason: str | None,
    extra: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "schema_version": "daemon_health_report_v1",
        "daemon_id": daemon_id,
        "icore_id": icore_id,
        "meta_hash": meta_hash,
        "tick": int(tick),
        "boot_count": int(boot_count),
        "ledger_head_hash": ledger_head_hash,
        "status": status,
        "paused_reason": paused_reason,
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        payload.update(extra)
    atomic_write_json(path, payload)


__all__ = ["write_health_report"]
