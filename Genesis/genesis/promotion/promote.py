from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Dict

from genesis.promotion.bid_policy import build_bid
from genesis.promotion.preflight import apply_local_spend, preflight_capsule
from genesis.promotion.protocol_budget import (
    ProtocolCaps,
    ProtocolRequest,
    apply_promotion,
    apply_request,
    check_caps,
    is_descriptor_novel,
    load_state as load_protocol_state,
    mark_descriptor,
    record_attempt,
    save_state as save_protocol_state,
    snapshot as protocol_snapshot,
)
from genesis.promotion.receipt_store import store_receipt


def _load_state(path: Path) -> Dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"epochs": {}}


def _save_state(path: Path, state: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _get_calls(state: Dict, epoch_id: str) -> int:
    return int(state.get("epochs", {}).get(epoch_id, {}).get("calls", 0))


def _shadow_margin_value(capsule: Dict, shadow_result: object | None) -> float:
    if shadow_result is None:
        return 0.0
    if capsule.get("artifact_type") == "POLICY" or capsule.get("x-system") is not None:
        return_bound = getattr(shadow_result, "return_bound", None)
        return_threshold = getattr(shadow_result, "return_threshold", None)
        cost_bound = getattr(shadow_result, "cost_bound", None)
        cost_threshold = getattr(shadow_result, "cost_threshold", None)
        if None in (return_bound, return_threshold, cost_bound, cost_threshold):
            return 0.0
        return_margin = float(return_bound) - float(return_threshold)
        cost_margin = float(cost_threshold) - float(cost_bound)
        return min(return_margin, cost_margin)

    bound = getattr(shadow_result, "bound", None)
    threshold = getattr(shadow_result, "threshold", None)
    if bound is None or threshold is None:
        return 0.0
    metric_clause = (capsule.get("contract", {}).get("statistical_spec", {}).get("metrics") or [{}])[0]
    direction = metric_clause.get("direction", "maximize")
    if direction == "minimize":
        return float(threshold) - float(bound)
    return float(bound) - float(threshold)


def _query_intents(capsule: Dict, bid: Dict) -> ProtocolRequest:
    metrics = (capsule.get("contract", {}).get("statistical_spec", {}).get("metrics") or [])
    stat_queries = len(metrics)
    privacy = bid.get("privacy_bid") or {}
    epsilon = float(privacy.get("epsilon", 0))
    delta = float(privacy.get("delta", 0))
    dp_queries = stat_queries if (epsilon > 0 or delta > 0) else 0
    robust_spec = capsule.get("contract", {}).get("robustness_spec") or {}
    robust_queries = 1 if robust_spec else 0
    return ProtocolRequest(
        cdel_calls=1,
        dp_queries=dp_queries,
        stat_queries=stat_queries,
        robust_queries=robust_queries,
    )

def _send_request(url: str, payload: Dict) -> Dict:
    data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
    response = json.loads(body)
    if response.get("result") not in {"PASS", "FAIL"}:
        raise ValueError("invalid response")
    if response.get("result") == "PASS" and "receipt" not in response:
        raise ValueError("PASS without receipt")
    if response.get("result") == "FAIL" and "receipt" in response:
        raise ValueError("FAIL with receipt")
    return response


def promote(
    capsule: Dict,
    config: Dict,
    epoch_id: str,
    receipts_dir: Path,
    state_path: Path,
    shadow_result: object | None,
    shadow_margin: float,
    descriptor: Dict | None = None,
    iteration_idx: int | None = None,
) -> Dict:
    state = _load_state(state_path)
    protocol_path = Path(config.get("protocol_budget_path", receipts_dir / "protocol_budget.json"))
    protocol_state = load_protocol_state(protocol_path)
    protocol_caps = ProtocolCaps.from_config(config)

    attempt_index = record_attempt(protocol_state, epoch_id)
    stride = int(config.get("promotion_stride", 1))
    if stride > 1 and (attempt_index % stride) != 0:
        snapshot = protocol_snapshot(protocol_state, epoch_id)
        save_protocol_state(protocol_path, protocol_state)
        return {
            "result": "FAIL",
            "promotion_attempted": False,
            "refusal_reason": "throttle_stride",
            "protocol_snapshot": snapshot,
        }

    descriptor_sig = None
    if descriptor:
        descriptor_sig = descriptor.get("operator_history_sig") or descriptor.get("descriptor_sig")
    novel = is_descriptor_novel(protocol_state, epoch_id, descriptor_sig)
    margin_value = _shadow_margin_value(capsule, shadow_result)
    min_margin = float(config.get("promotion_min_margin", shadow_margin))
    novelty_margin = float(config.get("promotion_novelty_margin", min_margin))
    if margin_value < min_margin:
        snapshot = protocol_snapshot(protocol_state, epoch_id)
        save_protocol_state(protocol_path, protocol_state)
        return {
            "result": "FAIL",
            "promotion_attempted": False,
            "refusal_reason": "shadow_margin_low",
            "protocol_snapshot": snapshot,
        }
    if not novel and margin_value < novelty_margin:
        snapshot = protocol_snapshot(protocol_state, epoch_id)
        save_protocol_state(protocol_path, protocol_state)
        return {
            "result": "FAIL",
            "promotion_attempted": False,
            "refusal_reason": "shadow_margin_low_non_novel",
            "protocol_snapshot": snapshot,
        }

    protocol_snap = protocol_snapshot(protocol_state, epoch_id)
    max_calls = protocol_caps.max_cdel_calls or int(config.get("max_cdel_calls_per_epoch", 0))
    calls_remaining = max_calls - protocol_snap["cdel_calls"] if max_calls > 0 else 1_000_000

    shadow_metric = getattr(shadow_result, "metric_value", None) if shadow_result is not None else None
    if shadow_metric is None and shadow_result is not None:
        shadow_metric = getattr(shadow_result, "return_value", None)
    bid = build_bid(capsule, config, shadow_metric=shadow_metric, calls_remaining=calls_remaining)
    ok, err = preflight_capsule(
        capsule,
        config,
        epoch_id,
        state,
        bid,
        shadow_result=shadow_result,
        shadow_margin=shadow_margin,
    )
    if not ok:
        snapshot = protocol_snapshot(protocol_state, epoch_id)
        save_protocol_state(protocol_path, protocol_state)
        return {
            "result": "FAIL",
            "promotion_attempted": False,
            "refusal_reason": err or "preflight_failed",
            "protocol_snapshot": snapshot,
        }

    request_caps = _query_intents(capsule, bid)
    ok, reason = check_caps(protocol_state, epoch_id, protocol_caps, request_caps)
    if not ok:
        snapshot = protocol_snapshot(protocol_state, epoch_id)
        save_protocol_state(protocol_path, protocol_state)
        return {
            "result": "FAIL",
            "promotion_attempted": False,
            "refusal_reason": reason or "protocol_cap",
            "protocol_snapshot": snapshot,
        }
    request = {"epoch_id": epoch_id, "capsule": capsule, "bid": bid}

    response = _send_request(config["cdel_url"], request)
    apply_local_spend(state, epoch_id, bid)
    _save_state(state_path, state)
    apply_request(protocol_state, epoch_id, request_caps)
    mark_descriptor(protocol_state, epoch_id, descriptor_sig)

    if response.get("result") == "PASS":
        record = store_receipt(response["receipt"], capsule, epoch_id, receipts_dir)
        apply_promotion(protocol_state, epoch_id)
        save_protocol_state(protocol_path, protocol_state)
        snapshot = protocol_snapshot(protocol_state, epoch_id)
        return {
            "result": "PASS",
            "receipt_hash": record["receipt_hash"],
            "audit_ref": record["audit_ref"],
            "bid": bid,
            "promotion_attempted": True,
            "protocol_snapshot": snapshot,
        }

    save_protocol_state(protocol_path, protocol_state)
    snapshot = protocol_snapshot(protocol_state, epoch_id)
    return {"result": "FAIL", "bid": bid, "promotion_attempted": True, "protocol_snapshot": snapshot}
