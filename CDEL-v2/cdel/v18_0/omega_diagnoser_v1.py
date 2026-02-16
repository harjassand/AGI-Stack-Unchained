"""Deterministic diagnoser for omega daemon v18.0."""

from __future__ import annotations

from typing import Any

from .omega_common_v1 import Q32_ONE, canon_hash_obj, fail, q32_int, validate_schema
from .omega_objectives_v1 import objective_target_q32


_SEARCH_SLOW_Q = int(Q32_ONE * 1.10)
_SEARCH_STALL_Q = int(Q32_ONE * 1.50)
_HOTLOOP_BOTTLENECK_Q = int(Q32_ONE * 0.98)
_BUILD_BOTTLENECK_Q = int(Q32_ONE * 0.50)
_PROMO_REJECT_Q = int(Q32_ONE * 0.50)
_VERIFIER_OVERHEAD_Q = int(Q32_ONE * 0.30)
_DOMAIN_VOID_Q = int(Q32_ONE * 0.30)
_POLYMATH_SCOUT_TTL_TICKS_U64 = 50
_PORTFOLIO_REGRESSION_WINDOW_U64 = 10
_PORTFOLIO_REGRESSION_FLOOR_PERCENT = 98


def _issue(
    *,
    issue_type: str,
    metric_id: str,
    severity_q: int,
    persistence_ticks_u64: int,
    evidence: list[str],
) -> dict[str, Any]:
    payload = {
        "issue_id": "sha256:" + "0" * 64,
        "issue_type": issue_type,
        "metric_id": metric_id,
        "severity_q32": {"q": max(0, int(severity_q))},
        "persistence_ticks_u64": max(0, int(persistence_ticks_u64)),
        "evidence": evidence,
    }
    no_id = dict(payload)
    no_id.pop("issue_id", None)
    payload["issue_id"] = canon_hash_obj(no_id)
    return payload


def diagnose(
    *,
    tick_u64: int,
    observation_report: dict[str, Any],
    objectives: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    metrics = observation_report.get("metrics")
    if not isinstance(metrics, dict):
        fail("SCHEMA_FAIL")

    evidence = [str(observation_report.get("report_id"))]
    issues: list[dict[str, Any]] = []

    metasearch_q = q32_int(metrics.get("metasearch_cost_ratio_q32"))
    if metasearch_q > _SEARCH_SLOW_Q:
        issues.append(
            _issue(
                issue_type="SEARCH_SLOW",
                metric_id="metasearch_cost_ratio_q32",
                severity_q=metasearch_q - _SEARCH_SLOW_Q,
                persistence_ticks_u64=1,
                evidence=evidence,
            )
        )
    if metasearch_q > _SEARCH_STALL_Q:
        issues.append(
            _issue(
                issue_type="SEARCH_STALL",
                metric_id="metasearch_cost_ratio_q32",
                severity_q=metasearch_q - _SEARCH_STALL_Q,
                persistence_ticks_u64=1,
                evidence=evidence,
            )
        )

    hotloop_q = q32_int(metrics.get("hotloop_top_share_q32"))
    if hotloop_q > _HOTLOOP_BOTTLENECK_Q:
        issues.append(
            _issue(
                issue_type="HOTLOOP_BOTTLENECK",
                metric_id="hotloop_top_share_q32",
                severity_q=hotloop_q - _HOTLOOP_BOTTLENECK_Q,
                persistence_ticks_u64=1,
                evidence=evidence,
            )
        )

    build_q = q32_int(metrics.get("build_link_fraction_q32"))
    if build_q > _BUILD_BOTTLENECK_Q:
        issues.append(
            _issue(
                issue_type="BUILD_BOTTLENECK",
                metric_id="build_link_fraction_q32",
                severity_q=build_q - _BUILD_BOTTLENECK_Q,
                persistence_ticks_u64=1,
                evidence=evidence,
            )
        )

    science_q = q32_int(metrics.get("science_rmse_q32"))
    science_target = objective_target_q32(objectives, "science_rmse_q32")
    if science_target is not None and science_q > science_target:
        issues.append(
            _issue(
                issue_type="SCIENCE_ACCURACY_STALL",
                metric_id="science_rmse_q32",
                severity_q=science_q - science_target,
                persistence_ticks_u64=1,
                evidence=evidence,
            )
        )

    reject_rate = metrics.get("promotion_reject_rate_rat")
    if isinstance(reject_rate, dict):
        num = int(reject_rate.get("num_u64", 0))
        den = int(reject_rate.get("den_u64", 1))
        q = (num * Q32_ONE) // max(1, den)
        if q > _PROMO_REJECT_Q:
            issues.append(
                _issue(
                    issue_type="PROMOTION_REJECT_RATE",
                    metric_id="promotion_reject_rate_rat",
                    severity_q=q - _PROMO_REJECT_Q,
                    persistence_ticks_u64=1,
                    evidence=evidence,
                )
            )

    verifier_overhead_q = q32_int(metrics.get("verifier_overhead_q32"))
    if verifier_overhead_q > _VERIFIER_OVERHEAD_Q:
        issues.append(
            _issue(
                issue_type="VERIFIER_OVERHEAD",
                metric_id="verifier_overhead_q32",
                severity_q=verifier_overhead_q - _VERIFIER_OVERHEAD_Q,
                persistence_ticks_u64=1,
                evidence=evidence,
            )
        )

    top_void_metric = metrics.get("top_void_score_q32")
    if isinstance(top_void_metric, dict):
        top_void_q = q32_int(top_void_metric)
        if top_void_q > _DOMAIN_VOID_Q:
            issues.append(
                _issue(
                    issue_type="DOMAIN_VOID_DETECTED",
                    metric_id="top_void_score_q32",
                    severity_q=top_void_q - _DOMAIN_VOID_Q,
                    persistence_ticks_u64=1,
                    evidence=evidence,
                )
            )

    scout_age_u64 = int(metrics.get("polymath_scout_age_ticks_u64", 0))
    if scout_age_u64 > _POLYMATH_SCOUT_TTL_TICKS_U64:
        issues.append(
            _issue(
                issue_type="POLYMATH_SCOUT_STALE",
                metric_id="polymath_scout_age_ticks_u64",
                severity_q=(int(scout_age_u64) - int(_POLYMATH_SCOUT_TTL_TICKS_U64)) * Q32_ONE,
                persistence_ticks_u64=1,
                evidence=evidence,
            )
        )

    metric_series = observation_report.get("metric_series")
    if isinstance(metric_series, dict):
        portfolio_rows = metric_series.get("polymath_portfolio_score_q32")
        if isinstance(portfolio_rows, list) and len(portfolio_rows) >= int(_PORTFOLIO_REGRESSION_WINDOW_U64):
            early_obj = portfolio_rows[-int(_PORTFOLIO_REGRESSION_WINDOW_U64)]
            late_obj = portfolio_rows[-1]
            if isinstance(early_obj, dict) and isinstance(late_obj, dict):
                early_q = q32_int(early_obj)
                late_q = q32_int(late_obj)
                if early_q > 0 and (int(late_q) * 100) < (int(early_q) * int(_PORTFOLIO_REGRESSION_FLOOR_PERCENT)):
                    issues.append(
                        _issue(
                            issue_type="POLYMATH_PORTFOLIO_REGRESSION",
                            metric_id="polymath_portfolio_score_q32",
                            severity_q=max(0, int(early_q) - int(late_q)),
                            persistence_ticks_u64=int(_PORTFOLIO_REGRESSION_WINDOW_U64),
                            evidence=evidence,
                        )
                    )

    domains_ready_for_conquer_u64 = int(metrics.get("domains_ready_for_conquer_u64", 0))
    if domains_ready_for_conquer_u64 > 0:
        issues.append(
            _issue(
                issue_type="DOMAIN_READY_FOR_CONQUER",
                metric_id="domains_ready_for_conquer_u64",
                severity_q=int(domains_ready_for_conquer_u64) * Q32_ONE,
                persistence_ticks_u64=1,
                evidence=evidence,
            )
        )

    blocked_license_u64 = int(metrics.get("domains_blocked_license_u64", 0))
    if blocked_license_u64 > 0:
        issues.append(
            _issue(
                issue_type="DOMAIN_BLOCKED_LICENSE",
                metric_id="domains_blocked_license_u64",
                severity_q=int(blocked_license_u64) * Q32_ONE,
                persistence_ticks_u64=1,
                evidence=evidence,
            )
        )

    blocked_size_u64 = int(metrics.get("domains_blocked_size_u64", 0))
    if blocked_size_u64 > 0:
        issues.append(
            _issue(
                issue_type="DOMAIN_BLOCKED_SIZE",
                metric_id="domains_blocked_size_u64",
                severity_q=int(blocked_size_u64) * Q32_ONE,
                persistence_ticks_u64=1,
                evidence=evidence,
            )
        )

    blocked_policy_u64 = int(metrics.get("domains_blocked_policy_u64", 0))
    if blocked_policy_u64 > 0:
        issues.append(
            _issue(
                issue_type="DOMAIN_BLOCKED_POLICY",
                metric_id="domains_blocked_policy_u64",
                severity_q=int(blocked_policy_u64) * Q32_ONE,
                persistence_ticks_u64=1,
                evidence=evidence,
            )
        )

    payload: dict[str, Any] = {
        "schema_version": "omega_issue_bundle_v1",
        "bundle_id": "sha256:" + "0" * 64,
        "tick_u64": int(tick_u64),
        "issues": issues,
    }
    no_id = dict(payload)
    no_id.pop("bundle_id", None)
    payload["bundle_id"] = canon_hash_obj(no_id)
    validate_schema(payload, "omega_issue_bundle_v1")
    return payload, canon_hash_obj(payload)


__all__ = ["diagnose"]
