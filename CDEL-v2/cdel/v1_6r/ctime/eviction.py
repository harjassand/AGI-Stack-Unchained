"""Macro eviction stub for v1.5r."""

from __future__ import annotations

from typing import Any


def compute_macro_evictions(
    *,
    epoch_dirs: list[Any],
    macros_dir: Any,
    active_macro_ids: list[str],
) -> dict[str, Any]:
    _ = epoch_dirs, macros_dir
    return {
        "schema": "macro_eviction_report_v1",
        "schema_version": 1,
        "evicted": [],
        "active_macro_ids": list(active_macro_ids),
    }
