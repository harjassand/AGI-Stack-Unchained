"""Deterministic objective J computation for continuity dominance gating."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common_v1 import canon_hash_obj, canonical_json_size, fail, make_budget_tracker, validate_schema
from .loaders_v1 import ArtifactRef, RegimeRef, load_artifact_ref


def _sum_schedule_cost(schedule_payload: Any) -> int:
    if isinstance(schedule_payload, dict):
        entries = schedule_payload.get("entries", [])
        if not isinstance(entries, list):
            fail("SCHEMA_ERROR", safe_halt=True)
        total = 0
        for row in entries:
            if isinstance(row, dict):
                total += int(row.get("cost_u64", row.get("cost", 0)) or 0)
            elif isinstance(row, int):
                total += int(row)
        return max(0, total)
    if isinstance(schedule_payload, list):
        return max(0, sum(int(x) for x in schedule_payload if isinstance(x, int)))
    fail("SCHEMA_ERROR", safe_halt=True)
    return 0


def _measure_inv(*, sigma_payload: Any, kernel_payload: Any) -> int:
    if isinstance(kernel_payload, dict):
        mode = str(kernel_payload.get("mode", "COUNT")).upper()
        if mode == "COUNT" and isinstance(sigma_payload, dict):
            failures = sigma_payload.get("invariant_failures", [])
            if isinstance(failures, list):
                return max(0, len(failures))
        if mode == "WEIGHTED" and isinstance(sigma_payload, dict):
            failures = sigma_payload.get("invariant_failures", [])
            if isinstance(failures, list):
                score = 0
                for row in failures:
                    if isinstance(row, dict):
                        score += int(row.get("weight_u64", 1))
                    else:
                        score += 1
                return max(0, score)
    fail("INV_MEASUREMENT_FAILURE", safe_halt=True)
    return 0


def _debt_length_from_sources(*, store_root: Path, refs: list[Any], tracker: Any) -> int:
    total = 0
    for row in refs:
        if not isinstance(row, dict):
            fail("SCHEMA_ERROR", safe_halt=True)
        loaded = load_artifact_ref(store_root, row)
        tracker.consume_items(1)
        tracker.consume_bytes_read(loaded.canonical_size)
        total += loaded.canonical_size
    return total


def compute_J(
    regime_ref: RegimeRef,
    sigma_ref: ArtifactRef,
    profile_ref: ArtifactRef,
    budgets: dict[str, Any],
) -> dict[str, Any]:
    """Compute deterministic J terms and weighted sum with full input binding."""

    store_root = Path(".").resolve()
    tracker = make_budget_tracker(budgets)

    sigma = load_artifact_ref(store_root, sigma_ref)
    profile = load_artifact_ref(store_root, profile_ref)
    tracker.consume_bytes_read(sigma.canonical_size + profile.canonical_size)

    profile_payload = profile.payload
    if not isinstance(profile_payload, dict):
        fail("SCHEMA_ERROR", safe_halt=True)
    validate_schema(profile_payload, "objective_J_profile_v1")

    enabled_terms_raw = profile_payload.get("enabled_terms")
    if not isinstance(enabled_terms_raw, list):
        fail("SCHEMA_ERROR", safe_halt=True)
    enabled_terms = [str(x) for x in enabled_terms_raw]

    weights = profile_payload.get("weights")
    if not isinstance(weights, dict):
        fail("SCHEMA_ERROR", safe_halt=True)

    terms: dict[str, int] = {
        "UDC_BASE": 0,
        "UDC_META": 0,
        "INV": 0,
        "TDL": 0,
        "KDL": 0,
        "EDL": 0,
        "CDL": 0,
        "CoDL": 0,
        "IDL": 0,
    }

    if "UDC_BASE" in enabled_terms:
        udc_ref = profile_payload.get("udc_schedule_ref")
        if not isinstance(udc_ref, dict):
            fail("MISSING_ARTIFACT", safe_halt=True)
        schedule = load_artifact_ref(store_root, udc_ref)
        tracker.consume_bytes_read(schedule.canonical_size)
        terms["UDC_BASE"] = _sum_schedule_cost(schedule.payload)

    if "UDC_META" in enabled_terms:
        meta_ref = profile_payload.get("meta_schedule_ref")
        if not isinstance(meta_ref, dict):
            fail("MISSING_ARTIFACT", safe_halt=True)
        schedule = load_artifact_ref(store_root, meta_ref)
        tracker.consume_bytes_read(schedule.canonical_size)
        terms["UDC_META"] = _sum_schedule_cost(schedule.payload)

    if "INV" in enabled_terms:
        kernels = profile_payload.get("measurement_kernels")
        if not isinstance(kernels, dict):
            fail("MISSING_ARTIFACT", safe_halt=True)
        inv_ref = kernels.get("INV")
        if not isinstance(inv_ref, dict):
            fail("MISSING_ARTIFACT", safe_halt=True)
        inv_kernel = load_artifact_ref(store_root, inv_ref)
        tracker.consume_bytes_read(inv_kernel.canonical_size)
        terms["INV"] = _measure_inv(sigma_payload=sigma.payload, kernel_payload=inv_kernel.payload)

    debt_sources = profile_payload.get("debt_sources", {})
    if debt_sources is None:
        debt_sources = {}
    if not isinstance(debt_sources, dict):
        fail("SCHEMA_ERROR", safe_halt=True)

    for term in ["TDL", "KDL", "EDL", "CDL", "CoDL", "IDL"]:
        if term not in enabled_terms:
            continue
        refs = debt_sources.get(term, [])
        if not isinstance(refs, list):
            fail("SCHEMA_ERROR", safe_halt=True)
        terms[term] = _debt_length_from_sources(store_root=store_root, refs=refs, tracker=tracker)

    horizons = profile_payload.get("amortization_horizons", {})
    if not isinstance(horizons, dict):
        fail("SCHEMA_ERROR", safe_halt=True)

    for debt_term in ["CDL", "CoDL", "KDL", "EDL", "IDL"]:
        horizon = int(horizons.get(debt_term, 1) or 1)
        if horizon < 1:
            fail("SCHEMA_ERROR", safe_halt=True)
        terms[debt_term] = terms[debt_term] // horizon

    # Weight mapping: lambda..eta correspond to first eight terms.
    weighted = (
        int(weights.get("lambda", 0)) * int(terms["UDC_BASE"])
        + int(weights.get("mu", 0)) * int(terms["UDC_META"])
        + int(weights.get("nu", 0)) * int(terms["INV"])
        + int(weights.get("alpha", 0)) * int(terms["TDL"])
        + int(weights.get("beta", 0)) * int(terms["KDL"])
        + int(weights.get("gamma", 0)) * int(terms["EDL"])
        + int(weights.get("delta", 0)) * int(terms["CDL"])
        + int(weights.get("eta", 0)) * int(terms["CoDL"])
        + int(terms["IDL"])
    )

    out_wo_id = {
        "schema_name": "objective_J_object_v1",
        "schema_version": "v19_0",
        "regime_id": canon_hash_obj(regime_ref),
        "sigma_id": sigma.ref["artifact_id"],
        "profile_id": profile.ref["artifact_id"],
        "budget_spec": budgets,
        "terms": terms,
        "weighted_sum": weighted,
        "epsilon": int(profile_payload.get("epsilon", 0)),
        "inputs": {
            "regime_ref": regime_ref,
            "sigma_ref": sigma_ref,
            "profile_ref": profile_ref,
        },
    }
    out = dict(out_wo_id)
    out["j_object_id"] = canon_hash_obj(out_wo_id)
    tracker.consume_bytes_write(canonical_json_size(out))
    return out


__all__ = ["compute_J"]
