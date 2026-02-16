"""Portfolio ledger helpers for polymath campaigns (v1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .omega_common_v1 import Q32_ONE, load_canon_dict, validate_schema

_SCHEMA_VERSION = "polymath_portfolio_v1"


def _empty_portfolio() -> dict[str, Any]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "domains": [],
        "portfolio_score_q32": {"q": 0},
    }


def _sorted_domains(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [dict(row) for row in rows if isinstance(row, dict)],
        key=lambda row: (str(row.get("domain_id", "")), str(row.get("train_sha256", ""))),
    )


def _recompute_portfolio_score_q32(portfolio: dict[str, Any]) -> None:
    rows = portfolio.get("domains")
    if not isinstance(rows, list) or not rows:
        portfolio["portfolio_score_q32"] = {"q": 0}
        return
    vals = [int((row or {}).get("best_metric_q32", 0)) for row in rows if isinstance(row, dict)]
    if not vals:
        portfolio["portfolio_score_q32"] = {"q": 0}
        return
    portfolio["portfolio_score_q32"] = {"q": int(sum(vals) // len(vals))}


def _entry_for(*, portfolio: dict[str, Any], domain_id: str, train_sha256: str) -> dict[str, Any]:
    rows = portfolio.get("domains")
    if not isinstance(rows, list):
        rows = []
        portfolio["domains"] = rows
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("domain_id", "")) == domain_id and str(row.get("train_sha256", "")) == train_sha256:
            return row
    row = {
        "domain_id": domain_id,
        "train_sha256": train_sha256,
        "level": "SINGLE",
        "best_metric_q32": 0,
        "last_metric_q32": 0,
        "last_conquer_tick_u64": 0,
        "last_improve_tick_u64": 0,
        "conquer_attempts_u64": 0,
        "cache_hit_rate_q32": 0,
    }
    rows.append(row)
    return row


def load_or_init_portfolio(path: Path) -> dict[str, Any]:
    if path.exists() and path.is_file():
        payload = load_canon_dict(path)
        validate_schema(payload, _SCHEMA_VERSION)
    else:
        payload = _empty_portfolio()
    rows = payload.get("domains")
    if not isinstance(rows, list):
        payload["domains"] = []
    payload["domains"] = _sorted_domains([row for row in payload.get("domains", []) if isinstance(row, dict)])
    _recompute_portfolio_score_q32(payload)
    validate_schema(payload, _SCHEMA_VERSION)
    return payload


def bootstrap_entry(
    *,
    portfolio: dict[str, Any],
    domain_id: str,
    train_sha256: str,
    baseline_metric_q32: int,
    tick_u64: int,
) -> dict[str, Any]:
    row = _entry_for(portfolio=portfolio, domain_id=domain_id, train_sha256=train_sha256)
    row["level"] = str(row.get("level", "SINGLE")) if str(row.get("level", "")).strip() else "SINGLE"
    row["best_metric_q32"] = int(max(int(row.get("best_metric_q32", 0)), int(baseline_metric_q32)))
    row["last_metric_q32"] = int(baseline_metric_q32)
    row["last_conquer_tick_u64"] = int(max(0, int(tick_u64)))
    if int(row["last_improve_tick_u64"]) <= 0:
        row["last_improve_tick_u64"] = int(max(0, int(tick_u64)))
    row["conquer_attempts_u64"] = int(max(0, int(row.get("conquer_attempts_u64", 0))))
    row["cache_hit_rate_q32"] = int(max(0, int(row.get("cache_hit_rate_q32", 0))))
    portfolio["domains"] = _sorted_domains([entry for entry in portfolio.get("domains", []) if isinstance(entry, dict)])
    _recompute_portfolio_score_q32(portfolio)
    validate_schema(portfolio, _SCHEMA_VERSION)
    return portfolio


def conquer_entry(
    *,
    portfolio: dict[str, Any],
    domain_id: str,
    train_sha256: str,
    metric_q32: int,
    improved_b: bool,
    cache_hit_b: bool,
    tick_u64: int,
) -> dict[str, Any]:
    row = _entry_for(portfolio=portfolio, domain_id=domain_id, train_sha256=train_sha256)
    prev_attempts = max(0, int(row.get("conquer_attempts_u64", 0)))
    next_attempts = prev_attempts + 1
    prev_rate = max(0, int(row.get("cache_hit_rate_q32", 0)))
    hit_q32 = int(Q32_ONE if bool(cache_hit_b) else 0)
    next_rate = int(((prev_rate * prev_attempts) + hit_q32) // max(1, next_attempts))

    best_metric_prev = int(row.get("best_metric_q32", 0))
    next_metric = int(metric_q32)
    row["last_metric_q32"] = next_metric
    row["last_conquer_tick_u64"] = int(max(0, int(tick_u64)))
    row["conquer_attempts_u64"] = int(next_attempts)
    row["cache_hit_rate_q32"] = int(next_rate)

    if next_metric >= best_metric_prev:
        row["best_metric_q32"] = int(next_metric)
    else:
        row["best_metric_q32"] = int(best_metric_prev)
    if bool(improved_b):
        row["last_improve_tick_u64"] = int(max(0, int(tick_u64)))
    row["level"] = str(row.get("level", "SINGLE")) if str(row.get("level", "")).strip() else "SINGLE"

    portfolio["domains"] = _sorted_domains([entry for entry in portfolio.get("domains", []) if isinstance(entry, dict)])
    _recompute_portfolio_score_q32(portfolio)
    validate_schema(portfolio, _SCHEMA_VERSION)
    return portfolio


def update_last_scout_tick(*, portfolio: dict[str, Any], tick_u64: int) -> dict[str, Any]:
    portfolio["last_scout_tick_u64"] = int(max(0, int(tick_u64)))
    portfolio["domains"] = _sorted_domains([entry for entry in portfolio.get("domains", []) if isinstance(entry, dict)])
    _recompute_portfolio_score_q32(portfolio)
    validate_schema(portfolio, _SCHEMA_VERSION)
    return portfolio


__all__ = [
    "bootstrap_entry",
    "conquer_entry",
    "load_or_init_portfolio",
    "update_last_scout_tick",
]
