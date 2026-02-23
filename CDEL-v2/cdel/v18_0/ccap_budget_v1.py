"""CCAP budget normalization and environment override helpers."""

from __future__ import annotations

import os
from typing import Any

from .omega_common_v1 import canon_hash_obj

_INT_LIMIT_KEYS: tuple[str, ...] = (
    "cpu_ms_max",
    "wall_ms_max",
    "mem_mb_max",
    "disk_mb_max",
    "fds_max",
    "procs_max",
    "threads_max",
)

CCAP_BUDGET_ENV_BY_KEY: dict[str, str] = {
    "cpu_ms_max": "OMEGA_CCAP_CPU_MS_MAX",
    "wall_ms_max": "OMEGA_CCAP_WALL_MS_MAX",
    "mem_mb_max": "OMEGA_CCAP_MEM_MB_MAX",
    "disk_mb_max": "OMEGA_CCAP_DISK_MB_MAX",
    "fds_max": "OMEGA_CCAP_FDS_MAX",
    "procs_max": "OMEGA_CCAP_PROCS_MAX",
    "threads_max": "OMEGA_CCAP_THREADS_MAX",
}


def _u64(value: Any, *, default: int = 0) -> int:
    try:
        out = int(value)
    except Exception:  # noqa: BLE001
        out = int(default)
    return int(max(0, out))


def normalize_ccap_budget_limits(limits: dict[str, Any] | None) -> dict[str, Any]:
    src = limits if isinstance(limits, dict) else {}
    out: dict[str, Any] = {key: _u64(src.get(key, 0), default=0) for key in _INT_LIMIT_KEYS}
    net = str(src.get("net", "forbidden")).strip() or "forbidden"
    out["net"] = net
    return out


def effective_ccap_budget_tuple(*, limits: dict[str, Any]) -> dict[str, int]:
    disk_mb_max = _u64(limits.get("disk_mb_max", 0), default=0)
    time_ms_max = _u64(limits.get("wall_ms_max", 0), default=0)
    stage_cost_budget = _u64(limits.get("cpu_ms_max", 0), default=0)
    artifact_bytes_max = int(disk_mb_max) * 1024 * 1024
    return {
        "disk_mb_max": int(disk_mb_max),
        "time_ms_max": int(time_ms_max),
        "stage_cost_budget": int(stage_cost_budget),
        "artifact_bytes_max": int(artifact_bytes_max),
    }


def resolve_effective_ccap_budget_profile(
    *,
    declared_budgets: dict[str, Any] | None,
    minimum_int_limits: dict[str, int] | None = None,
) -> dict[str, Any]:
    declared_limits = normalize_ccap_budget_limits(declared_budgets)
    effective_limits = dict(declared_limits)
    env_overrides: dict[str, str] = {}
    for key, env_key in CCAP_BUDGET_ENV_BY_KEY.items():
        raw = os.environ.get(env_key)
        if raw is None:
            continue
        text = str(raw).strip()
        if not text:
            continue
        effective_limits[key] = _u64(text, default=effective_limits.get(key, 0))
        env_overrides[env_key] = str(effective_limits[key])

    mins = minimum_int_limits if isinstance(minimum_int_limits, dict) else {}
    for key, min_value in mins.items():
        if key not in _INT_LIMIT_KEYS:
            continue
        effective_limits[key] = int(max(_u64(effective_limits.get(key, 0), default=0), _u64(min_value, default=0)))

    profile = {
        "limits": normalize_ccap_budget_limits(effective_limits),
        "tuple": effective_ccap_budget_tuple(limits=effective_limits),
        "env_overrides": {k: str(v) for k, v in sorted(env_overrides.items())},
    }
    profile["profile_id"] = canon_hash_obj(
        {
            "schema_version": "ccap_effective_budget_profile_v1",
            "declared_limits": declared_limits,
            "limits": profile["limits"],
            "tuple": profile["tuple"],
            "env_overrides": profile["env_overrides"],
        }
    )
    return profile


__all__ = [
    "CCAP_BUDGET_ENV_BY_KEY",
    "effective_ccap_budget_tuple",
    "normalize_ccap_budget_limits",
    "resolve_effective_ccap_budget_profile",
]
