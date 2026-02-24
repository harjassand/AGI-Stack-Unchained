"""Pinned Tier A/Tier B J-comparison semantics for Phase 4C."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common_v1 import canon_hash_obj, load_canon_dict, validate_schema

_Q32_ONE = 1 << 32

_LEGACY_MIRROR_METRIC_IDS = {
    "median_stps_non_noop_q32",
    "non_noop_ticks_per_min_q32",
    "promotions_u64_q32",
    "activation_success_u64_q32",
}


def _q32_box(value: Any) -> int | None:
    if not isinstance(value, dict):
        return None
    if set(value.keys()) != {"q"}:
        return None
    raw = value.get("q")
    if not isinstance(raw, int):
        return None
    return int(raw)


def _legacy_flat_metric_q32_from_ccap_receipt(*, ccap_receipt: dict[str, Any], metric_id: str) -> int | None:
    score = ccap_receipt.get("score_cand_summary")
    if not isinstance(score, dict):
        score = ccap_receipt.get("scorecard_summary")
    if not isinstance(score, dict):
        return None

    if metric_id == "median_stps_non_noop_q32":
        raw = score.get("median_stps_non_noop_q32")
        if isinstance(raw, int):
            return int(raw)
        return None
    if metric_id == "non_noop_ticks_per_min_q32":
        raw = score.get("non_noop_ticks_per_min_f64")
        if isinstance(raw, bool):
            return None
        if isinstance(raw, int):
            return int(max(0, raw) * _Q32_ONE)
        if isinstance(raw, float):
            if raw != raw or raw in (float("inf"), float("-inf")):
                return None
            return int(round(max(0.0, raw) * float(_Q32_ONE)))
        return None
    if metric_id == "promotions_u64_q32":
        raw = score.get("promotions_u64")
        if isinstance(raw, int):
            return int(max(0, raw) << 32)
        return None
    if metric_id == "activation_success_u64_q32":
        raw = score.get("activation_success_u64")
        if isinstance(raw, int):
            return int(max(0, raw) << 32)
        return None
    return None


def aggregate_executed_suite_metric_q32(
    *,
    benchmark_run_receipt_v2: dict[str, Any],
    metric_id: str,
) -> int | None:
    executed_suites = benchmark_run_receipt_v2.get("executed_suites")
    if not isinstance(executed_suites, list) or not executed_suites:
        return None
    values: list[int] = []
    for row in executed_suites:
        if not isinstance(row, dict):
            raise RuntimeError("SCHEMA_FAIL")
        metrics = row.get("metrics")
        if not isinstance(metrics, dict):
            raise RuntimeError("SCHEMA_FAIL")
        q32 = _q32_box(metrics.get(metric_id))
        if q32 is not None:
            values.append(int(q32))
    if not values:
        return None
    return int(sum(values) // len(values))


def extract_metric_q32_from_ccap_receipt(
    *,
    ccap_receipt: dict[str, Any],
    metric_id: str,
    require_consistent_mirror_b: bool = True,
) -> tuple[int | None, str]:
    if not isinstance(ccap_receipt, dict):
        raise RuntimeError("SCHEMA_FAIL")

    from_v2: int | None = None
    benchmark_run_receipt_v2 = ccap_receipt.get("benchmark_run_receipt_v2")
    if isinstance(benchmark_run_receipt_v2, dict):
        schema_version = str(benchmark_run_receipt_v2.get("schema_version", "")).strip()
        if schema_version != "benchmark_run_receipt_v2":
            raise RuntimeError("SCHEMA_FAIL")
        from_v2 = aggregate_executed_suite_metric_q32(
            benchmark_run_receipt_v2=benchmark_run_receipt_v2,
            metric_id=metric_id,
        )

    from_legacy = _legacy_flat_metric_q32_from_ccap_receipt(
        ccap_receipt=ccap_receipt,
        metric_id=metric_id,
    )
    if (
        require_consistent_mirror_b
        and metric_id in _LEGACY_MIRROR_METRIC_IDS
        and from_v2 is not None
        and from_legacy is not None
        and int(from_v2) != int(from_legacy)
    ):
        raise RuntimeError("NONDETERMINISM")

    if from_v2 is not None:
        return int(from_v2), "V2_EXECUTED_SUITES_MEAN"
    if from_legacy is not None:
        return int(from_legacy), "LEGACY_FLAT"
    return None, "MISSING"


def extract_required_q32_metrics_from_ccap_receipt(
    *,
    ccap_receipt: dict[str, Any],
    required_metric_ids: list[str] | tuple[str, ...],
    require_consistent_mirror_b: bool = True,
) -> dict[str, Any]:
    normalized_ids = sorted({str(metric_id).strip() for metric_id in required_metric_ids if str(metric_id).strip()})
    metrics_q32: dict[str, int] = {}
    metric_source_by_id: dict[str, str] = {}
    missing_metric_ids: list[str] = []
    for metric_id in normalized_ids:
        metric_q32, source = extract_metric_q32_from_ccap_receipt(
            ccap_receipt=ccap_receipt,
            metric_id=metric_id,
            require_consistent_mirror_b=require_consistent_mirror_b,
        )
        metric_source_by_id[metric_id] = str(source)
        if metric_q32 is None:
            missing_metric_ids.append(metric_id)
            continue
        metrics_q32[metric_id] = int(metric_q32)
    return {
        "metrics_q32": metrics_q32,
        "metric_source_by_id": metric_source_by_id,
        "missing_metric_ids_v1": missing_metric_ids,
    }


def build_ccap_receipt_metric_index_for_state_root(
    *,
    state_root: Path,
    required_metric_ids: list[str] | tuple[str, ...],
    require_consistent_mirror_b: bool = True,
) -> dict[int, dict[str, int]]:
    root = Path(state_root).resolve()
    dispatch_root = root / "dispatch"
    if not dispatch_root.exists() or not dispatch_root.is_dir():
        return {}

    normalized_ids = sorted({str(metric_id).strip() for metric_id in required_metric_ids if str(metric_id).strip()})
    if not normalized_ids:
        return {}

    index: dict[int, dict[str, int]] = {}
    for dispatch_dir in sorted(dispatch_root.iterdir(), key=lambda row: row.as_posix()):
        if not dispatch_dir.exists() or not dispatch_dir.is_dir() or dispatch_dir.is_symlink():
            continue
        dispatch_rows = sorted(dispatch_dir.glob("*.omega_dispatch_receipt_v1.json"), key=lambda row: row.as_posix())
        if not dispatch_rows:
            continue
        dispatch_payload = load_canon_dict(dispatch_rows[-1])
        if str(dispatch_payload.get("schema_version", "")).strip() != "omega_dispatch_receipt_v1":
            continue
        tick_u64 = int(dispatch_payload.get("tick_u64", -1))
        if tick_u64 < 0:
            continue

        verifier_dir = dispatch_dir / "verifier"
        if not verifier_dir.exists() or not verifier_dir.is_dir():
            continue
        receipt_rows = sorted(verifier_dir.glob("*.ccap_receipt_v1.json"), key=lambda row: row.as_posix())
        if not receipt_rows:
            continue
        for receipt_path in receipt_rows:
            receipt = load_canon_dict(receipt_path)
            if str(receipt.get("schema_version", "")).strip() != "ccap_receipt_v1":
                continue
            if canon_hash_obj(receipt) != ("sha256:" + receipt_path.name.split(".", 1)[0].split("_", 1)[1]):
                raise RuntimeError("NONDETERMINISM")
            extracted = extract_required_q32_metrics_from_ccap_receipt(
                ccap_receipt=receipt,
                required_metric_ids=normalized_ids,
                require_consistent_mirror_b=require_consistent_mirror_b,
            )
            metrics_q32_raw = extracted.get("metrics_q32")
            if not isinstance(metrics_q32_raw, dict):
                raise RuntimeError("SCHEMA_FAIL")
            if not metrics_q32_raw:
                continue
            existing = index.get(int(tick_u64), {})
            merged = dict(existing)
            for metric_id, value in sorted(metrics_q32_raw.items(), key=lambda kv: str(kv[0])):
                metric_key = str(metric_id).strip()
                metric_q32 = int(value)
                if metric_key in merged and int(merged[metric_key]) != metric_q32:
                    raise RuntimeError("NONDETERMINISM")
                merged[metric_key] = metric_q32
            index[int(tick_u64)] = merged
    return {int(tick): dict(rows) for tick, rows in sorted(index.items(), key=lambda kv: int(kv[0]))}


def evaluate_j_comparison(
    *,
    profile: dict[str, Any],
    j19_window_q32: list[int],
    j20_window_q32: list[int],
) -> dict[str, Any]:
    validate_schema(profile, "j_comparison_v1")
    if not isinstance(j19_window_q32, list) or not isinstance(j20_window_q32, list):
        raise RuntimeError("SCHEMA_FAIL")
    if not j19_window_q32 or not j20_window_q32:
        raise RuntimeError("SCHEMA_FAIL")
    if len(j19_window_q32) != len(j20_window_q32):
        raise RuntimeError("SCHEMA_FAIL")

    margin_q32 = int((profile.get("window_rule") or {}).get("margin_q32", 0))
    per_tick_floor_enabled_b = bool(profile.get("per_tick_floor_enabled_b", False))
    epsilon_tick_q32 = int(profile.get("epsilon_tick_q32", 0))
    if margin_q32 < 0 or epsilon_tick_q32 < 0:
        raise RuntimeError("SCHEMA_FAIL")

    sum19 = int(sum(int(row) for row in j19_window_q32))
    sum20 = int(sum(int(row) for row in j20_window_q32))
    window_len = int(len(j19_window_q32))
    threshold = int(sum19 + (margin_q32 * window_len))
    window_rule_pass_b = sum20 >= threshold

    per_tick_floor_pass_b = True
    if per_tick_floor_enabled_b:
        for lhs, rhs in zip(j20_window_q32, j19_window_q32):
            if int(lhs) < (int(rhs) - epsilon_tick_q32):
                per_tick_floor_pass_b = False
                break

    pass_b = bool(window_rule_pass_b and (per_tick_floor_pass_b or not per_tick_floor_enabled_b))
    reason_codes: list[str] = []
    if not window_rule_pass_b:
        reason_codes.append("SHADOW_J_WINDOW_RULE_FAIL")
    if per_tick_floor_enabled_b and not per_tick_floor_pass_b:
        reason_codes.append("SHADOW_J_PER_TICK_FLOOR_FAIL")
    return {
        "schema_name": "shadow_j_comparison_receipt_v1",
        "schema_version": "v19_0",
        "window_rule": dict(profile.get("window_rule", {})),
        "window_len_u64": window_len,
        "sum_j19_window_q32": sum19,
        "sum_j20_window_q32": sum20,
        "threshold_q32": threshold,
        "window_rule_pass_b": bool(window_rule_pass_b),
        "per_tick_floor_enabled_b": bool(per_tick_floor_enabled_b),
        "per_tick_floor_pass_b": bool(per_tick_floor_pass_b),
        "epsilon_tick_q32": int(epsilon_tick_q32),
        "pass_b": pass_b,
        "reason_codes": sorted(set(reason_codes)),
    }


__all__ = [
    "aggregate_executed_suite_metric_q32",
    "build_ccap_receipt_metric_index_for_state_root",
    "evaluate_j_comparison",
    "extract_metric_q32_from_ccap_receipt",
    "extract_required_q32_metrics_from_ccap_receipt",
]
