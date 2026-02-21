"""Deterministic epistemic action market helpers."""

from __future__ import annotations

from typing import Any

from ..common_v1 import canon_hash_obj, ensure_sha256, fail, validate_schema, verify_object_id

_ACTION_KINDS: tuple[str, ...] = ("FETCH", "SEGMENT", "INFER", "REDUCE", "SEAL")
_DISPATCHABLE_ACTION_KINDS: tuple[str, ...] = ("REDUCE", "SEAL")


def _ordered_unique_sha(values: list[str]) -> list[str]:
    ordered = sorted({ensure_sha256(v, reason="SCHEMA_FAIL") for v in values})
    return ordered


def _ordered_unique_metric_ids(values: list[str]) -> list[str]:
    out = sorted({str(v).strip() for v in values if str(v).strip()})
    return out


def _q32_div(num: int, den: int) -> int:
    den_i = max(1, int(den))
    return int((int(num) << 32) // den_i)


def _action_factor(action_kind: str) -> int:
    return {
        "FETCH": 1,
        "SEGMENT": 2,
        "INFER": 3,
        "REDUCE": 4,
        "SEAL": 5,
    }.get(str(action_kind), 1)


def build_default_action_market_profile() -> dict[str, Any]:
    payload = {
        "schema_version": "epistemic_action_market_profile_v1",
        "profile_id": "sha256:" + ("0" * 64),
        "eufc_window_ticks_u64": 8,
        "allowed_action_kinds": list(_ACTION_KINDS),
        "dispatchable_action_kinds": list(_DISPATCHABLE_ACTION_KINDS),
        "tie_break_policy": "SCORE_DESC_ACTION_ASC_BID_ID_ASC",
    }
    payload["profile_id"] = canon_hash_obj({k: v for k, v in payload.items() if k != "profile_id"})
    validate_schema(payload, "epistemic_action_market_profile_v1")
    verify_object_id(payload, id_field="profile_id")
    return payload


def build_action_market_inputs_manifest(
    *,
    tick_u64: int,
    market_profile_id: str,
    prior_market_state_id: str | None,
    observation_report_hash: str,
    observation_metric_ids: list[str],
    eligible_capsule_ids: list[str],
    eligible_graph_ids: list[str],
    eligible_ecac_ids: list[str],
    eligible_eufc_ids: list[str],
    eufc_window_receipt_rows: list[dict[str, Any]],
    eufc_window_open_tick_u64: int,
    eufc_window_close_tick_u64: int,
) -> dict[str, Any]:
    market_profile_id = ensure_sha256(market_profile_id, reason="SCHEMA_FAIL")
    prior_state = None if prior_market_state_id is None else ensure_sha256(prior_market_state_id, reason="SCHEMA_FAIL")
    observation_report_hash = ensure_sha256(observation_report_hash, reason="SCHEMA_FAIL")

    ordered_window_rows: list[tuple[int, str]] = []
    for row in eufc_window_receipt_rows:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        eufc_id = ensure_sha256(row.get("eufc_id"), reason="SCHEMA_FAIL")
        row_tick = int(row.get("tick_u64", 0))
        if row_tick < 0:
            fail("SCHEMA_FAIL")
        ordered_window_rows.append((row_tick, eufc_id))
    ordered_window_rows.sort(key=lambda item: (int(item[0]), str(item[1])))
    eufc_window_receipt_ids = [row[1] for row in ordered_window_rows]

    payload = {
        "schema_version": "epistemic_action_market_inputs_v1",
        "inputs_manifest_id": "sha256:" + ("0" * 64),
        "tick_u64": int(tick_u64),
        "market_profile_id": market_profile_id,
        "prior_market_state_id": prior_state,
        "ordering_rule": "CANON_ASC_SHA256",
        "eligible_capsule_ids": _ordered_unique_sha(list(eligible_capsule_ids)),
        "eligible_graph_ids": _ordered_unique_sha(list(eligible_graph_ids)),
        "eligible_ecac_ids": _ordered_unique_sha(list(eligible_ecac_ids)),
        "eligible_eufc_ids": _ordered_unique_sha(list(eligible_eufc_ids)),
        "observation_metric_ids": _ordered_unique_metric_ids(list(observation_metric_ids)),
        "observation_report_hash": observation_report_hash,
        "eufc_window_mode": "EUFC_WINDOW",
        "eufc_window_receipt_ids": list(eufc_window_receipt_ids),
        "eufc_window_receipt_ordering_rule": "TICK_ASC_THEN_ID_ASC",
        "eufc_window_open_tick_u64": int(eufc_window_open_tick_u64),
        "eufc_window_close_tick_u64": int(eufc_window_close_tick_u64),
    }
    payload["inputs_manifest_id"] = canon_hash_obj(
        {k: v for k, v in payload.items() if k != "inputs_manifest_id"}
    )
    validate_schema(payload, "epistemic_action_market_inputs_v1")
    verify_object_id(payload, id_field="inputs_manifest_id")
    return payload


def build_action_bids(
    *,
    inputs_manifest: dict[str, Any],
    market_profile: dict[str, Any],
) -> list[dict[str, Any]]:
    validate_schema(inputs_manifest, "epistemic_action_market_inputs_v1")
    validate_schema(market_profile, "epistemic_action_market_profile_v1")
    inputs_manifest_id = verify_object_id(inputs_manifest, id_field="inputs_manifest_id")
    market_profile_id = verify_object_id(market_profile, id_field="profile_id")

    allowed = list(market_profile.get("allowed_action_kinds") or [])
    dispatchable = {str(row) for row in list(market_profile.get("dispatchable_action_kinds") or [])}
    if not allowed:
        fail("SCHEMA_FAIL")
    allowed_sorted = sorted(str(row) for row in allowed)
    if not set(allowed_sorted).issubset(set(_ACTION_KINDS)):
        fail("SCHEMA_FAIL")
    if not dispatchable.issubset(set(_ACTION_KINDS)):
        fail("SCHEMA_FAIL")

    base_score = (
        len(list(inputs_manifest.get("eligible_capsule_ids") or []))
        + (2 * len(list(inputs_manifest.get("eligible_graph_ids") or [])))
        + len(list(inputs_manifest.get("eligible_eufc_ids") or []))
        + len(list(inputs_manifest.get("observation_metric_ids") or []))
    )
    if base_score < 0:
        fail("SCHEMA_FAIL")

    bids: list[dict[str, Any]] = []
    for action_kind in allowed_sorted:
        factor = _action_factor(action_kind)
        dispatchable_b = bool(action_kind in dispatchable)
        predicted_delta = int(base_score * factor) << 16
        predicted_cost = max(1, int(factor) << 16)
        score = _q32_div(predicted_delta, predicted_cost)
        if not dispatchable_b:
            score = 0
        feature_binding_hash = canon_hash_obj(
            {
                "schema_version": "epistemic_action_market_feature_binding_v1",
                "inputs_manifest_id": inputs_manifest_id,
                "market_profile_id": market_profile_id,
                "action_kind": action_kind,
                "base_score_u64": int(base_score),
                "factor_u64": int(factor),
                "dispatchable_b": bool(dispatchable_b),
            }
        )
        bid = {
            "schema_version": "epistemic_action_bid_v1",
            "bid_id": "sha256:" + ("0" * 64),
            "tick_u64": int(inputs_manifest.get("tick_u64", 0)),
            "inputs_manifest_id": inputs_manifest_id,
            "market_profile_id": market_profile_id,
            "action_kind": str(action_kind),
            "dispatchable_b": bool(dispatchable_b),
            "predicted_delta_j_q32": int(predicted_delta),
            "predicted_cost_q32": int(predicted_cost),
            "score_q32": int(score),
            "feature_binding_hash": str(feature_binding_hash),
        }
        bid["bid_id"] = canon_hash_obj({k: v for k, v in bid.items() if k != "bid_id"})
        validate_schema(bid, "epistemic_action_bid_v1")
        verify_object_id(bid, id_field="bid_id")
        bids.append(bid)
    return bids


def build_action_bid_set(
    *,
    inputs_manifest: dict[str, Any],
    market_profile: dict[str, Any],
    bids: list[dict[str, Any]],
) -> dict[str, Any]:
    validate_schema(inputs_manifest, "epistemic_action_market_inputs_v1")
    validate_schema(market_profile, "epistemic_action_market_profile_v1")
    inputs_manifest_id = verify_object_id(inputs_manifest, id_field="inputs_manifest_id")
    market_profile_id = verify_object_id(market_profile, id_field="profile_id")
    bid_ids = sorted(verify_object_id(dict(row), id_field="bid_id") for row in bids)
    payload = {
        "schema_version": "epistemic_action_bid_set_v1",
        "bid_set_id": "sha256:" + ("0" * 64),
        "tick_u64": int(inputs_manifest.get("tick_u64", 0)),
        "inputs_manifest_id": inputs_manifest_id,
        "market_profile_id": market_profile_id,
        "bid_ids": bid_ids,
    }
    payload["bid_set_id"] = canon_hash_obj({k: v for k, v in payload.items() if k != "bid_set_id"})
    validate_schema(payload, "epistemic_action_bid_set_v1")
    verify_object_id(payload, id_field="bid_set_id")
    return payload


def select_action_winner(
    *,
    inputs_manifest: dict[str, Any],
    market_profile: dict[str, Any],
    bid_set: dict[str, Any],
    bids: list[dict[str, Any]],
) -> dict[str, Any]:
    validate_schema(inputs_manifest, "epistemic_action_market_inputs_v1")
    validate_schema(market_profile, "epistemic_action_market_profile_v1")
    validate_schema(bid_set, "epistemic_action_bid_set_v1")
    inputs_manifest_id = verify_object_id(inputs_manifest, id_field="inputs_manifest_id")
    market_profile_id = verify_object_id(market_profile, id_field="profile_id")
    bid_set_id = verify_object_id(bid_set, id_field="bid_set_id")

    rows: list[dict[str, Any]] = []
    rank_rows: list[tuple[int, str, str]] = []
    tie_break_path = [
        "ACTION_MARKET_RANK:score_q32_desc",
        "ACTION_MARKET_RANK:action_kind_asc",
        "ACTION_MARKET_RANK:bid_id_asc",
    ]
    for row in bids:
        validate_schema(row, "epistemic_action_bid_v1")
        bid_id = verify_object_id(row, id_field="bid_id")
        if ensure_sha256(row.get("inputs_manifest_id"), reason="SCHEMA_FAIL") != inputs_manifest_id:
            fail("NONDETERMINISTIC")
        if ensure_sha256(row.get("market_profile_id"), reason="SCHEMA_FAIL") != market_profile_id:
            fail("NONDETERMINISTIC")
        action_kind = str(row.get("action_kind", "")).strip()
        score = int(row.get("score_q32", 0))
        dispatchable_b = bool(row.get("dispatchable_b", False))
        eligible_b = bool(dispatchable_b)
        skip_reason = "N/A" if eligible_b else "NON_DISPATCHABLE"
        rows.append(
            {
                "action_kind": action_kind,
                "bid_id": bid_id,
                "dispatchable_b": bool(dispatchable_b),
                "score_q32": int(max(0, score)),
                "eligible_b": bool(eligible_b),
                "skip_reason": skip_reason,
            }
        )
        if eligible_b:
            rank_rows.append((int(max(0, score)), action_kind, bid_id))

    rows.sort(key=lambda item: (str(item["action_kind"]), str(item["bid_id"])))
    outcome = "NOOP"
    winner_action_kind: str | None = None
    winner_bid_id: str | None = None
    if rank_rows:
        rank_rows.sort(key=lambda item: (-int(item[0]), str(item[1]), str(item[2])))
        _score, winner_action_kind, winner_bid_id = rank_rows[0]
        tie_break_path.append(f"ACTION_MARKET_WINNER:{winner_action_kind}")
        outcome = "OK"
    else:
        tie_break_path.append("ACTION_MARKET_NO_ELIGIBLE:NOOP")

    payload = {
        "schema_version": "epistemic_action_selection_receipt_v1",
        "selection_id": "sha256:" + ("0" * 64),
        "tick_u64": int(inputs_manifest.get("tick_u64", 0)),
        "inputs_manifest_id": inputs_manifest_id,
        "market_profile_id": market_profile_id,
        "bid_set_id": bid_set_id,
        "winner_action_kind": winner_action_kind,
        "winner_bid_id": winner_bid_id,
        "outcome": outcome,
        "tie_break_path": tie_break_path,
        "candidates": rows,
    }
    payload["selection_id"] = canon_hash_obj({k: v for k, v in payload.items() if k != "selection_id"})
    validate_schema(payload, "epistemic_action_selection_receipt_v1")
    verify_object_id(payload, id_field="selection_id")
    return payload


def compute_credit_key(*, selection_id: str, action_kind: str, produced_capsule_id: str) -> str:
    return canon_hash_obj(
        {
            "schema_version": "epistemic_action_credit_key_v1",
            "selection_id": ensure_sha256(selection_id, reason="SCHEMA_FAIL"),
            "action_kind": str(action_kind).strip(),
            "produced_capsule_id": ensure_sha256(produced_capsule_id, reason="SCHEMA_FAIL"),
        }
    )


def settle_action_selection(
    *,
    inputs_manifest: dict[str, Any],
    selection_receipt: dict[str, Any],
    produced_capsule_id: str | None,
) -> dict[str, Any]:
    validate_schema(inputs_manifest, "epistemic_action_market_inputs_v1")
    validate_schema(selection_receipt, "epistemic_action_selection_receipt_v1")
    inputs_manifest_id = verify_object_id(inputs_manifest, id_field="inputs_manifest_id")
    selection_id = verify_object_id(selection_receipt, id_field="selection_id")
    if ensure_sha256(selection_receipt.get("inputs_manifest_id"), reason="SCHEMA_FAIL") != inputs_manifest_id:
        fail("NONDETERMINISTIC")

    winner_action_kind_raw = selection_receipt.get("winner_action_kind")
    winner_bid_id_raw = selection_receipt.get("winner_bid_id")
    winner_action_kind = None if winner_action_kind_raw is None else str(winner_action_kind_raw).strip()
    winner_bid_id = None if winner_bid_id_raw is None else ensure_sha256(winner_bid_id_raw, reason="SCHEMA_FAIL")
    capsule_id = None if produced_capsule_id is None else ensure_sha256(produced_capsule_id, reason="SCHEMA_FAIL")
    credit_key = None
    outcome = "NO_CREDIT"
    if winner_action_kind and winner_bid_id and capsule_id:
        credit_key = compute_credit_key(
            selection_id=selection_id,
            action_kind=winner_action_kind,
            produced_capsule_id=capsule_id,
        )
        outcome = "SETTLED"

    payload = {
        "schema_version": "epistemic_action_settlement_receipt_v1",
        "action_settlement_id": "sha256:" + ("0" * 64),
        "tick_u64": int(inputs_manifest.get("tick_u64", 0)),
        "inputs_manifest_id": inputs_manifest_id,
        "selection_id": selection_id,
        "winner_action_kind": winner_action_kind,
        "winner_bid_id": winner_bid_id,
        "produced_capsule_id": capsule_id,
        "credit_key": credit_key,
        "eufc_window_mode": "EUFC_WINDOW",
        "eufc_window_receipt_ids": list(inputs_manifest.get("eufc_window_receipt_ids") or []),
        "outcome": outcome,
    }
    payload["action_settlement_id"] = canon_hash_obj(
        {k: v for k, v in payload.items() if k != "action_settlement_id"}
    )
    validate_schema(payload, "epistemic_action_settlement_receipt_v1")
    verify_object_id(payload, id_field="action_settlement_id")
    return payload


def verify_action_market_replay(
    *,
    inputs_manifest: dict[str, Any],
    market_profile: dict[str, Any],
    observed_bids: list[dict[str, Any]],
    observed_bid_set: dict[str, Any],
    observed_selection: dict[str, Any],
    observed_settlement: dict[str, Any],
    produced_capsule_id: str | None,
) -> dict[str, Any]:
    expected_bids = build_action_bids(inputs_manifest=inputs_manifest, market_profile=market_profile)
    if len(expected_bids) != len(observed_bids):
        fail("NONDETERMINISTIC")
    expected_by_action = {str(row.get("action_kind", "")): row for row in expected_bids}
    observed_by_action = {str(row.get("action_kind", "")): row for row in observed_bids}
    if set(expected_by_action.keys()) != set(observed_by_action.keys()):
        fail("NONDETERMINISTIC")
    for action_kind in sorted(expected_by_action.keys()):
        if canon_hash_obj(expected_by_action[action_kind]) != canon_hash_obj(observed_by_action[action_kind]):
            fail("NONDETERMINISTIC")

    expected_bid_set = build_action_bid_set(
        inputs_manifest=inputs_manifest,
        market_profile=market_profile,
        bids=expected_bids,
    )
    if canon_hash_obj(expected_bid_set) != canon_hash_obj(observed_bid_set):
        fail("NONDETERMINISTIC")

    expected_selection = select_action_winner(
        inputs_manifest=inputs_manifest,
        market_profile=market_profile,
        bid_set=expected_bid_set,
        bids=expected_bids,
    )
    if canon_hash_obj(expected_selection) != canon_hash_obj(observed_selection):
        fail("NONDETERMINISTIC")

    expected_settlement = settle_action_selection(
        inputs_manifest=inputs_manifest,
        selection_receipt=expected_selection,
        produced_capsule_id=produced_capsule_id,
    )
    if canon_hash_obj(expected_settlement) != canon_hash_obj(observed_settlement):
        fail("NONDETERMINISTIC")

    return {
        "inputs_manifest_id": verify_object_id(inputs_manifest, id_field="inputs_manifest_id"),
        "selection_id": verify_object_id(expected_selection, id_field="selection_id"),
        "action_settlement_id": verify_object_id(expected_settlement, id_field="action_settlement_id"),
    }


__all__ = [
    "build_action_bid_set",
    "build_action_bids",
    "build_action_market_inputs_manifest",
    "build_default_action_market_profile",
    "compute_credit_key",
    "select_action_winner",
    "settle_action_selection",
    "verify_action_market_replay",
]

