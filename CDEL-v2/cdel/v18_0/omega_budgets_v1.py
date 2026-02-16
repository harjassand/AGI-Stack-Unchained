"""Loader and budget utilities for omega budgets v1."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .omega_common_v1 import canon_hash_obj, fail, load_canon_dict, q32_int, q32_obj, validate_schema


BUDGET_FIELDS = ("cpu_cost_q32", "build_cost_q32", "verifier_cost_q32", "disk_bytes_u64")


def load_budgets(path: Path) -> tuple[dict[str, Any], str]:
    obj = load_canon_dict(path)
    if obj.get("schema_version") != "omega_budgets_v1":
        fail("SCHEMA_FAIL")
    validate_schema(obj, "omega_budgets_v1")
    return obj, canon_hash_obj(obj)


def default_remaining(budgets: dict[str, Any]) -> dict[str, Any]:
    return {
        "cpu_cost_q32": q32_obj(q32_int(budgets.get("max_cpu_cost_q32_per_day"))),
        "build_cost_q32": q32_obj(q32_int(budgets.get("max_build_cost_q32_per_day"))),
        "verifier_cost_q32": q32_obj(q32_int(budgets.get("max_verifier_cost_q32_per_day"))),
        "disk_bytes_u64": int(budgets.get("max_disk_bytes_per_day", 0)),
    }


def has_budget(remaining: dict[str, Any], *, cost_q32: int) -> bool:
    cpu = q32_int(remaining.get("cpu_cost_q32"))
    build = q32_int(remaining.get("build_cost_q32"))
    verify = q32_int(remaining.get("verifier_cost_q32"))
    return cpu >= cost_q32 and build >= cost_q32 and verify >= cost_q32


def debit_budget(remaining: dict[str, Any], *, cost_q32: int, disk_bytes: int) -> dict[str, Any]:
    out = {
        "cpu_cost_q32": q32_obj(max(0, q32_int(remaining.get("cpu_cost_q32")) - cost_q32)),
        "build_cost_q32": q32_obj(max(0, q32_int(remaining.get("build_cost_q32")) - cost_q32)),
        "verifier_cost_q32": q32_obj(max(0, q32_int(remaining.get("verifier_cost_q32")) - cost_q32)),
        "disk_bytes_u64": max(0, int(remaining.get("disk_bytes_u64", 0)) - max(0, int(disk_bytes))),
    }
    return out


__all__ = ["BUDGET_FIELDS", "debit_budget", "default_remaining", "has_budget", "load_budgets"]
