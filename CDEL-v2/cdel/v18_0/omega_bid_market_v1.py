"""Deterministic bid-market scheduler (predation market) for Omega v18.x.

This module is used by both orchestrator coordinators and the replay verifier.
Like other Omega components, the verifier shares logic with the coordinator
and validates via hash binding + recomputation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .omega_budgets_v1 import has_budget
from .omega_common_v1 import Q32_ONE, canon_hash_obj, fail, load_canon_dict, q32_int, q32_mul, q32_obj, validate_schema, write_hashed_json


_CONFIG_NAME = "omega_bid_market_config_v1.json"

def _with_id_field(payload: dict[str, Any], id_field: str) -> dict[str, Any]:
    obj = dict(payload)
    no_id = dict(obj)
    no_id.pop(id_field, None)
    obj[id_field] = canon_hash_obj(no_id)
    return obj


def load_bid_market_config(path: Path) -> tuple[dict[str, Any], str]:
    obj = load_canon_dict(path)
    if str(obj.get("schema_version", "")).strip() != "omega_bid_market_config_v1":
        fail("SCHEMA_FAIL")
    validate_schema(obj, "omega_bid_market_config_v1")
    return obj, canon_hash_obj(obj)


def load_optional_bid_market_config(config_dir: Path) -> tuple[dict[str, Any] | None, str | None]:
    path = config_dir / _CONFIG_NAME
    if not path.exists():
        return None, None
    if not path.is_file():
        fail("SCHEMA_FAIL")
    return load_bid_market_config(path)


def bid_market_enabled(cfg: dict[str, Any] | None) -> bool:
    if not isinstance(cfg, dict):
        return False
    return bool(cfg.get("enabled", False))


def _cfg_q32(cfg: dict[str, Any], key: str, *, default_q: int, min_q: int | None = None, max_q: int | None = None) -> int:
    raw = cfg.get(key)
    q = default_q if raw is None else q32_int(raw)
    if min_q is not None:
        q = max(int(min_q), int(q))
    if max_q is not None:
        q = min(int(max_q), int(q))
    return int(q)


def _cfg_u64(cfg: dict[str, Any], key: str, *, default_u64: int, min_u64: int | None = None) -> int:
    raw = cfg.get(key)
    value = default_u64 if raw is None else int(raw)
    if min_u64 is not None:
        value = max(int(min_u64), int(value))
    return int(value)


def resolve_bidder_params(cfg: dict[str, Any], campaign_id: str) -> tuple[int, int, int]:
    """Return (roi_q32, confidence_q32, horizon_ticks_u64) with defaults+overrides."""

    default_roi_q32 = _cfg_q32(cfg, "default_predicted_roi_q32", default_q=int(Q32_ONE), min_q=0)
    default_conf_q32 = _cfg_q32(cfg, "default_confidence_q32", default_q=int(Q32_ONE // 2), min_q=0, max_q=int(Q32_ONE))
    default_horizon_u64 = _cfg_u64(cfg, "default_horizon_ticks_u64", default_u64=1, min_u64=1)

    overrides = cfg.get("campaign_overrides") or []
    if not isinstance(overrides, list):
        fail("SCHEMA_FAIL")
    for row in overrides:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        if str(row.get("campaign_id", "")).strip() != str(campaign_id):
            continue
        roi_q32 = default_roi_q32
        conf_q32 = default_conf_q32
        horizon_u64 = default_horizon_u64
        if row.get("predicted_roi_q32") is not None:
            roi_q32 = max(0, q32_int(row.get("predicted_roi_q32")))
        if row.get("confidence_q32") is not None:
            conf_q32 = q32_int(row.get("confidence_q32"))
            conf_q32 = max(0, min(int(Q32_ONE), int(conf_q32)))
        if row.get("horizon_ticks_u64") is not None:
            horizon_u64 = max(1, int(row.get("horizon_ticks_u64")))
        return int(roi_q32), int(conf_q32), int(horizon_u64)

    return int(default_roi_q32), int(default_conf_q32), int(default_horizon_u64)


def resolve_settlement_params(cfg: dict[str, Any]) -> dict[str, int]:
    return {
        "initial_bankroll_q32": _cfg_q32(cfg, "initial_bankroll_q32", default_q=int(Q32_ONE), min_q=0),
        "initial_credibility_q32": _cfg_q32(cfg, "initial_credibility_q32", default_q=int(Q32_ONE // 2), min_q=0, max_q=int(Q32_ONE)),
        "credibility_lr_q32": _cfg_q32(cfg, "credibility_lr_q32", default_q=int(Q32_ONE // 2), min_q=0, max_q=int(Q32_ONE)),
        "min_credibility_q32": _cfg_q32(cfg, "min_credibility_q32", default_q=0, min_q=0, max_q=int(Q32_ONE)),
        "error_cap_q32": _cfg_q32(cfg, "error_cap_q32", default_q=int(Q32_ONE), min_q=1),
        "bankroll_penalty_rate_q32": _cfg_q32(cfg, "bankroll_penalty_rate_q32", default_q=int(Q32_ONE // 2), min_q=0, max_q=int(Q32_ONE)),
        "bankroll_reward_rate_q32": _cfg_q32(cfg, "bankroll_reward_rate_q32", default_q=int(Q32_ONE // 20), min_q=0, max_q=int(Q32_ONE)),
        "bankroll_disable_threshold_q32": _cfg_q32(cfg, "bankroll_disable_threshold_q32", default_q=int(Q32_ONE // 4), min_q=0),
        "disable_after_ticks_u64": _cfg_u64(cfg, "disable_after_ticks_u64", default_u64=3, min_u64=1),
    }


def _campaign_ids_from_registry(registry: dict[str, Any]) -> list[str]:
    caps = registry.get("capabilities")
    if not isinstance(caps, list):
        fail("SCHEMA_FAIL")
    out: set[str] = set()
    for row in caps:
        if isinstance(row, dict):
            cid = str(row.get("campaign_id", "")).strip()
            if cid:
                out.add(cid)
    return sorted(out)


def bootstrap_market_state(
    *,
    tick_u64: int,
    config_hash: str,
    registry_hash: str,
    registry: dict[str, Any],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    params = resolve_settlement_params(cfg)
    states = []
    for campaign_id in _campaign_ids_from_registry(registry):
        states.append(
            {
                "campaign_id": campaign_id,
                "bankroll_q32": q32_obj(int(params["initial_bankroll_q32"])),
                "credibility_q32": q32_obj(int(params["initial_credibility_q32"])),
                "bankruptcy_streak_u64": 0,
                "disabled_b": False,
                "disabled_reason": "N/A",
            }
        )
    obj: dict[str, Any] = {
        "schema_version": "bid_market_state_v1",
        "state_id": "sha256:" + ("0" * 64),
        "tick_u64": int(tick_u64),
        "prev_state_id": None,
        "config_hash": str(config_hash),
        "registry_hash": str(registry_hash),
        "campaign_states": states,
    }
    obj = _with_id_field(obj, "state_id")
    validate_schema(obj, "bid_market_state_v1")
    return obj


def write_bid_market_state(out_dir: Path, payload: dict[str, Any]) -> tuple[Path, dict[str, Any], str]:
    path, obj, digest = write_hashed_json(out_dir, "bid_market_state_v1.json", payload)
    validate_schema(obj, "bid_market_state_v1")
    return path, obj, digest


def load_latest_bid_market_state(state_dir: Path) -> dict[str, Any] | None:
    if not state_dir.exists() or not state_dir.is_dir():
        return None
    rows = sorted(state_dir.glob("sha256_*.bid_market_state_v1.json"), key=lambda p: p.as_posix())
    if not rows:
        return None
    best: dict[str, Any] | None = None
    best_tick = -1
    for path in rows:
        payload = load_canon_dict(path)
        if payload.get("schema_version") != "bid_market_state_v1":
            continue
        tick = int(payload.get("tick_u64", -1))
        if tick > best_tick:
            best_tick = tick
            best = payload
    if best is None:
        return None
    validate_schema(best, "bid_market_state_v1")
    return best


def _objective_metric_ids(objectives: dict[str, Any]) -> list[str]:
    rows = objectives.get("metrics")
    if not isinstance(rows, list):
        fail("SCHEMA_FAIL")
    ids = []
    for row in rows:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        metric_id = str(row.get("metric_id", "")).strip()
        if not metric_id:
            fail("SCHEMA_FAIL")
        ids.append(metric_id)
    return ids


def J_q32_from_observation(*, observation_report: dict[str, Any], objectives: dict[str, Any]) -> int:
    metrics = observation_report.get("metrics")
    if not isinstance(metrics, dict):
        fail("SCHEMA_FAIL")
    total = 0
    for metric_id in _objective_metric_ids(objectives):
        row = metrics.get(metric_id)
        if not isinstance(row, dict) or "q" not in row:
            fail("SCHEMA_FAIL")
        total += int(row.get("q", 0))
    return int(total)


def J_prev_q32_from_metric_series(*, observation_report: dict[str, Any], objectives: dict[str, Any]) -> int | None:
    series = observation_report.get("metric_series")
    if not isinstance(series, dict):
        return None
    total = 0
    any_found = False
    for metric_id in _objective_metric_ids(objectives):
        rows = series.get(metric_id)
        if not isinstance(rows, list) or len(rows) < 2:
            return None
        prev = rows[-2]
        if not isinstance(prev, dict) or "q" not in prev:
            fail("SCHEMA_FAIL")
        total += int(prev.get("q", 0))
        any_found = True
    return int(total) if any_found else None


def _market_state_map(market_state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = market_state.get("campaign_states")
    if not isinstance(rows, list):
        fail("SCHEMA_FAIL")
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        cid = str(row.get("campaign_id", "")).strip()
        if not cid:
            fail("SCHEMA_FAIL")
        out[cid] = row
    return out


def _clamp_q32(value: int, *, lo: int, hi: int) -> int:
    return int(max(int(lo), min(int(hi), int(value))))


def _apply_bankruptcy_rules(
    *,
    campaign_state: dict[str, Any],
    bankroll_q32: int,
    disable_threshold_q32: int,
    disable_after_ticks_u64: int,
) -> tuple[int, bool, str, int]:
    disabled_b = bool(campaign_state.get("disabled_b", False))
    if disabled_b:
        return (
            max(0, int(campaign_state.get("bankruptcy_streak_u64", 0))),
            True,
            str(campaign_state.get("disabled_reason", "") or "N/A"),
            int(bankroll_q32),
        )

    streak = max(0, int(campaign_state.get("bankruptcy_streak_u64", 0)))
    if int(bankroll_q32) < int(disable_threshold_q32):
        streak += 1
    else:
        streak = 0
    if streak >= int(disable_after_ticks_u64):
        return streak, True, "BANKROLL_BELOW_THRESHOLD", int(bankroll_q32)
    return streak, False, "N/A", int(bankroll_q32)


def settle_and_advance_market_state(
    *,
    tick_u64: int,
    config_hash: str,
    registry_hash: str,
    cfg: dict[str, Any],
    registry: dict[str, Any],
    objectives: dict[str, Any],
    prev_market_state: dict[str, Any] | None,
    prev_market_state_hash: str | None,
    prev_selection_receipt: dict[str, Any] | None,
    prev_selection_hash: str | None,
    prev_observation_report: dict[str, Any] | None,
    prev_observation_hash: str | None,
    cur_observation_report: dict[str, Any],
    cur_observation_hash: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (settlement_receipt, market_state_after)."""

    params = resolve_settlement_params(cfg)
    disable_threshold_q32 = int(params["bankroll_disable_threshold_q32"])
    disable_after_u64 = int(params["disable_after_ticks_u64"])

    # Compute J_cur always; J_prev is optional.
    J_cur = int(J_q32_from_observation(observation_report=cur_observation_report, objectives=objectives))
    J_prev: int | None = None
    if isinstance(prev_observation_report, dict):
        J_prev = int(J_q32_from_observation(observation_report=prev_observation_report, objectives=objectives))
    else:
        derived = J_prev_q32_from_metric_series(observation_report=cur_observation_report, objectives=objectives)
        if derived is not None:
            J_prev = int(derived)

    settled_tick_u64: int | None = None
    winner_campaign_id: str | None = None
    winner_bid: dict[str, Any] | None = None
    outcome = "GENESIS"

    if isinstance(prev_selection_receipt, dict) and prev_selection_hash is not None:
        settled_tick_u64 = max(0, int(prev_selection_receipt.get("tick_u64", 0)))
        winner = prev_selection_receipt.get("winner")
        if isinstance(winner, dict) and str(prev_selection_receipt.get("outcome", "")) == "OK":
            winner_campaign_id = str(winner.get("campaign_id", "")).strip() or None
            winner_bid = dict(winner)
        outcome = "OK"

    realized_delta: int | None = None
    if J_prev is not None:
        realized_delta = int(J_cur - J_prev)

    # Start from previous state when available; otherwise bootstrap.
    state_before = dict(prev_market_state) if isinstance(prev_market_state, dict) else None
    if state_before is None:
        # Tick-local bootstrap; state_id must be deterministic for hashing.
        state_before = bootstrap_market_state(
            tick_u64=max(0, int(tick_u64) - 1),
            config_hash=config_hash,
            registry_hash=registry_hash,
            registry=registry,
            cfg=cfg,
        )

    cmap = _market_state_map(state_before)

    # Winner-only update.
    updates = {
        "winner_bankroll_before_q32": q32_obj(0),
        "winner_bankroll_after_q32": q32_obj(0),
        "winner_credibility_before_q32": q32_obj(0),
        "winner_credibility_after_q32": q32_obj(0),
        "disabled_campaign_ids": [],
    }

    if outcome == "OK" and winner_campaign_id and realized_delta is not None and winner_bid is not None:
        cstate = cmap.get(winner_campaign_id)
        if cstate is None:
            fail("SCHEMA_FAIL")
        bankroll_old = max(0, q32_int(cstate.get("bankroll_q32")))
        cred_old = _clamp_q32(q32_int(cstate.get("credibility_q32")), lo=0, hi=int(Q32_ONE))

        pred = max(0, q32_int(winner_bid.get("predicted_delta_J_q32")))
        conf = _clamp_q32(q32_int(winner_bid.get("confidence_q32")), lo=0, hi=int(Q32_ONE))

        abs_err = abs(int(realized_delta) - int(pred))
        error_norm = min(int(Q32_ONE), int((int(abs_err) << 32) // max(1, int(params["error_cap_q32"]))))
        accuracy = int(Q32_ONE - error_norm)

        cred_new = int(cred_old + q32_mul(int(params["credibility_lr_q32"]), int(accuracy - cred_old)))
        cred_new = _clamp_q32(cred_new, lo=int(params["min_credibility_q32"]), hi=int(Q32_ONE))

        penalty_fraction = q32_mul(q32_mul(int(params["bankroll_penalty_rate_q32"]), int(conf)), int(error_norm))
        reward_fraction = q32_mul(q32_mul(int(params["bankroll_reward_rate_q32"]), int(conf)), int(accuracy))
        factor = max(0, int(Q32_ONE - int(penalty_fraction) + int(reward_fraction)))
        bankroll_new = max(0, q32_mul(int(bankroll_old), int(factor)))

        cstate = dict(cstate)
        cstate["bankroll_q32"] = q32_obj(int(bankroll_new))
        cstate["credibility_q32"] = q32_obj(int(cred_new))
        cmap[winner_campaign_id] = cstate

        updates["winner_bankroll_before_q32"] = q32_obj(int(bankroll_old))
        updates["winner_bankroll_after_q32"] = q32_obj(int(bankroll_new))
        updates["winner_credibility_before_q32"] = q32_obj(int(cred_old))
        updates["winner_credibility_after_q32"] = q32_obj(int(cred_new))

    # Apply bankruptcy streak/disable rules to all campaigns (including non-winner).
    newly_disabled: list[str] = []
    next_states: list[dict[str, Any]] = []
    for campaign_id in sorted(cmap.keys()):
        row = dict(cmap[campaign_id])
        bankroll_q = max(0, q32_int(row.get("bankroll_q32")))
        streak, disabled_b, disabled_reason, bankroll_q = _apply_bankruptcy_rules(
            campaign_state=row,
            bankroll_q32=bankroll_q,
            disable_threshold_q32=disable_threshold_q32,
            disable_after_ticks_u64=disable_after_u64,
        )
        was_disabled = bool(row.get("disabled_b", False))
        row["bankruptcy_streak_u64"] = int(streak)
        row["disabled_b"] = bool(disabled_b)
        row["disabled_reason"] = str(disabled_reason if disabled_reason else "N/A")
        row["bankroll_q32"] = q32_obj(int(bankroll_q))
        if (not was_disabled) and bool(disabled_b):
            newly_disabled.append(campaign_id)
        next_states.append(row)

    updates["disabled_campaign_ids"] = list(newly_disabled)

    state_after: dict[str, Any] = {
        "schema_version": "bid_market_state_v1",
        "state_id": "sha256:" + ("0" * 64),
        "tick_u64": int(tick_u64),
        "prev_state_id": (state_before.get("state_id") if prev_market_state is not None else None),
        "config_hash": str(config_hash),
        "registry_hash": str(registry_hash),
        "campaign_states": next_states,
    }
    state_after = _with_id_field(state_after, "state_id")
    validate_schema(state_after, "bid_market_state_v1")
    state_after_hash = canon_hash_obj(state_after)

    receipt = {
        "schema_version": "bid_settlement_receipt_v1",
        "receipt_id": "sha256:" + ("0" * 64),
        "tick_u64": int(tick_u64),
        "settled_tick_u64": settled_tick_u64,
        "selection_receipt_hash": prev_selection_hash,
        "prev_observation_report_hash": prev_observation_hash,
        "cur_observation_report_hash": cur_observation_hash,
        "J_prev_q32": (q32_obj(int(J_prev)) if J_prev is not None else None),
        "J_cur_q32": q32_obj(int(J_cur)),
        "realized_delta_J_q32": (q32_obj(int(realized_delta)) if realized_delta is not None else None),
        "winner_campaign_id": winner_campaign_id,
        "winner_bid": (dict(winner_bid) if winner_bid is not None else None),
        "market_state_before_hash": prev_market_state_hash,
        "market_state_after_hash": state_after_hash,
        "updates": updates,
        "outcome": outcome,
    }
    receipt = _with_id_field(receipt, "receipt_id")
    validate_schema(receipt, "bid_settlement_receipt_v1")
    return receipt, state_after


def write_bid_settlement_receipt(out_dir: Path, payload: dict[str, Any]) -> tuple[Path, dict[str, Any], str]:
    path, obj, digest = write_hashed_json(out_dir, "bid_settlement_receipt_v1.json", payload)
    validate_schema(obj, "bid_settlement_receipt_v1")
    return path, obj, digest


def build_bid_v1(
    *,
    tick_u64: int,
    campaign_id: str,
    capability_id: str,
    observation_report_hash: str,
    market_state_hash: str,
    config_hash: str,
    registry_hash: str,
    roi_q32: int,
    confidence_q32: int,
    horizon_ticks_u64: int,
    predicted_cost_q32: int,
) -> dict[str, Any]:
    predicted_cost_q32 = max(1, int(predicted_cost_q32))
    roi_q32 = max(0, int(roi_q32))
    confidence_q32 = _clamp_q32(int(confidence_q32), lo=0, hi=int(Q32_ONE))
    horizon_ticks_u64 = max(1, int(horizon_ticks_u64))

    inputs_hash = canon_hash_obj(
        {
            "tick_u64": int(tick_u64),
            "campaign_id": str(campaign_id),
            "capability_id": str(capability_id),
            "observation_report_hash": str(observation_report_hash),
            "market_state_hash": str(market_state_hash),
            "config_hash": str(config_hash),
            "registry_hash": str(registry_hash),
        }
    )
    evidence_hash = canon_hash_obj(
        {
            "inputs_hash": str(inputs_hash),
            "roi_q32": q32_obj(int(roi_q32)),
            "confidence_q32": q32_obj(int(confidence_q32)),
            "horizon_ticks_u64": int(horizon_ticks_u64),
            "predicted_cost_q32": q32_obj(int(predicted_cost_q32)),
        }
    )
    predicted_delta = max(0, int(q32_mul(int(roi_q32), int(predicted_cost_q32))))

    obj: dict[str, Any] = {
        "schema_version": "bid_v1",
        "bid_id": "sha256:" + ("0" * 64),
        "tick_u64": int(tick_u64),
        "campaign_id": str(campaign_id),
        "capability_id": str(capability_id),
        "inputs_hash": str(inputs_hash),
        "observation_report_hash": str(observation_report_hash),
        "market_state_hash": str(market_state_hash),
        "config_hash": str(config_hash),
        "registry_hash": str(registry_hash),
        "predicted_delta_J_q32": q32_obj(int(predicted_delta)),
        "predicted_cost_q32": q32_obj(int(predicted_cost_q32)),
        "confidence_q32": q32_obj(int(confidence_q32)),
        "horizon_ticks_u64": int(horizon_ticks_u64),
        "evidence_hash": str(evidence_hash),
    }
    obj = _with_id_field(obj, "bid_id")
    validate_schema(obj, "bid_v1")
    return obj


def write_bid_v1(out_dir: Path, payload: dict[str, Any]) -> tuple[Path, dict[str, Any], str]:
    path, obj, digest = write_hashed_json(out_dir, "bid_v1.json", payload)
    validate_schema(obj, "bid_v1")
    return path, obj, digest


def build_bid_set_v1(
    *,
    tick_u64: int,
    observation_report_hash: str,
    market_state_hash: str,
    config_hash: str,
    registry_hash: str,
    bids_by_campaign: dict[str, str],
) -> dict[str, Any]:
    rows = [{"campaign_id": cid, "bid_hash": bids_by_campaign[cid]} for cid in sorted(bids_by_campaign.keys())]
    obj: dict[str, Any] = {
        "schema_version": "bid_set_v1",
        "bid_set_id": "sha256:" + ("0" * 64),
        "tick_u64": int(tick_u64),
        "observation_report_hash": str(observation_report_hash),
        "market_state_hash": str(market_state_hash),
        "config_hash": str(config_hash),
        "registry_hash": str(registry_hash),
        "bids": rows,
    }
    obj = _with_id_field(obj, "bid_set_id")
    validate_schema(obj, "bid_set_v1")
    return obj


def write_bid_set_v1(out_dir: Path, payload: dict[str, Any]) -> tuple[Path, dict[str, Any], str]:
    path, obj, digest = write_hashed_json(out_dir, "bid_set_v1.json", payload)
    validate_schema(obj, "bid_set_v1")
    return path, obj, digest


def _rank_key(
    *,
    score_q32: int,
    roi_q32: int,
    credibility_q32: int,
    confidence_q32: int,
    campaign_id: str,
) -> tuple[int, int, int, int, str]:
    # Sort descending by numeric keys, then ascending by campaign_id.
    return (
        -int(score_q32),
        -int(roi_q32),
        -int(credibility_q32),
        -int(confidence_q32),
        str(campaign_id),
    )


def select_winner(
    *,
    tick_u64: int,
    observation_report_hash: str,
    market_state: dict[str, Any],
    market_state_hash: str,
    config_hash: str,
    registry_hash: str,
    bid_set_hash: str,
    bids: dict[str, dict[str, Any]],
    prev_state: dict[str, Any],
) -> dict[str, Any]:
    cmap = _market_state_map(market_state)
    cooldowns = prev_state.get("cooldowns") or {}
    budget_remaining = prev_state.get("budget_remaining") or {}
    if not isinstance(cooldowns, dict) or not isinstance(budget_remaining, dict):
        fail("SCHEMA_FAIL")

    candidates = []
    eligible = []
    for campaign_id in sorted(bids.keys()):
        bid = bids[campaign_id]
        bid_hash = canon_hash_obj(bid)
        cstate = cmap.get(campaign_id)
        if cstate is None:
            fail("SCHEMA_FAIL")
        credibility_q32 = _clamp_q32(q32_int(cstate.get("credibility_q32")), lo=0, hi=int(Q32_ONE))
        confidence_q32 = _clamp_q32(q32_int(bid.get("confidence_q32")), lo=0, hi=int(Q32_ONE))
        pred_delta = max(0, q32_int(bid.get("predicted_delta_J_q32")))
        pred_cost = max(1, q32_int(bid.get("predicted_cost_q32")))

        roi_q32 = int((int(pred_delta) << 32) // max(1, int(pred_cost)))
        score_q32 = int(q32_mul(int(roi_q32), int(credibility_q32)))

        cooldown_next = int(((cooldowns.get(campaign_id) or {}).get("next_tick_allowed_u64", 0)))
        if cooldown_next > int(tick_u64):
            eligible_b = False
            skip_reason = "COOLDOWN"
        elif not has_budget(budget_remaining, cost_q32=int(pred_cost)):
            eligible_b = False
            skip_reason = "BUDGET"
        else:
            eligible_b = True
            skip_reason = "N/A"

        row = {
            "campaign_id": campaign_id,
            "bid_hash": bid_hash,
            "eligible_b": bool(eligible_b),
            "skip_reason": str(skip_reason),
            "score_q32": q32_obj(int(score_q32)),
            "roi_q32": q32_obj(int(roi_q32)),
        }
        candidates.append((row, _rank_key(score_q32=score_q32, roi_q32=roi_q32, credibility_q32=credibility_q32, confidence_q32=confidence_q32, campaign_id=campaign_id)))
        if eligible_b:
            eligible.append(
                (
                    campaign_id,
                    bid_hash,
                    score_q32,
                    roi_q32,
                    credibility_q32,
                    confidence_q32,
                    pred_delta,
                    pred_cost,
                    int(bid.get("horizon_ticks_u64", 1)),
                    str(bid.get("evidence_hash", "")),
                )
            )

    # Final deterministic ordering includes skipped candidates too.
    candidates_sorted = [row for row, _ in sorted(candidates, key=lambda t: t[1])]

    tie_break_path = [
        "MARKET_RANK:score_q32_desc",
        "MARKET_RANK:roi_q32_desc",
        "MARKET_RANK:credibility_q32_desc",
        "MARKET_RANK:confidence_q32_desc",
        "MARKET_RANK:campaign_id_asc",
        *(
            f"MARKET_CANDIDATE:{row['campaign_id']}:{'ELIGIBLE' if row['eligible_b'] else 'SKIP'}:{row['skip_reason']}"
            for row in candidates_sorted
        ),
    ]

    winner_payload = None
    outcome = "NOOP"
    if eligible:
        # Re-rank only eligible using the same key (descending numeric, then campaign_id).
        eligible_sorted = sorted(
            eligible,
            key=lambda r: _rank_key(
                score_q32=r[2],
                roi_q32=r[3],
                credibility_q32=r[4],
                confidence_q32=r[5],
                campaign_id=r[0],
            ),
        )
        (cid, bid_hash, score_q, roi_q, cred_q, conf_q, pred_delta, pred_cost, horizon_u64, evidence_hash) = eligible_sorted[0]
        winner_payload = {
            "campaign_id": cid,
            "bid_hash": bid_hash,
            "score_q32": q32_obj(int(score_q)),
            "roi_q32": q32_obj(int(roi_q)),
            "credibility_q32": q32_obj(int(cred_q)),
            "confidence_q32": q32_obj(int(conf_q)),
            "predicted_delta_J_q32": q32_obj(int(pred_delta)),
            "predicted_cost_q32": q32_obj(int(pred_cost)),
            "horizon_ticks_u64": int(max(1, int(horizon_u64))),
            "evidence_hash": str(evidence_hash),
        }
        outcome = "OK"
        tie_break_path.append(f"MARKET_WINNER:{cid}")
    else:
        tie_break_path.append("MARKET_NO_ELIGIBLE:NOOP")

    receipt = {
        "schema_version": "bid_selection_receipt_v1",
        "receipt_id": "sha256:" + ("0" * 64),
        "tick_u64": int(tick_u64),
        "observation_report_hash": str(observation_report_hash),
        "market_state_hash": str(market_state_hash),
        "bid_set_hash": str(bid_set_hash),
        "config_hash": str(config_hash),
        "registry_hash": str(registry_hash),
        "winner": winner_payload,
        "candidates": candidates_sorted,
        "tie_break_path": tie_break_path,
        "outcome": outcome,
    }
    receipt = _with_id_field(receipt, "receipt_id")
    validate_schema(receipt, "bid_selection_receipt_v1")
    return receipt


def write_bid_selection_receipt(out_dir: Path, payload: dict[str, Any]) -> tuple[Path, dict[str, Any], str]:
    path, obj, digest = write_hashed_json(out_dir, "bid_selection_receipt_v1.json", payload)
    validate_schema(obj, "bid_selection_receipt_v1")
    return path, obj, digest


def _decision_inputs_hash(plan: dict[str, Any]) -> str:
    return canon_hash_obj(
        {
            "tick_u64": plan.get("tick_u64"),
            "observation_report_hash": plan.get("observation_report_hash"),
            "issue_bundle_hash": plan.get("issue_bundle_hash"),
            "policy_hash": plan.get("policy_hash"),
            "registry_hash": plan.get("registry_hash"),
            "budgets_hash": plan.get("budgets_hash"),
            "action_kind": plan.get("action_kind"),
            "campaign_id": plan.get("campaign_id"),
            "capability_id": plan.get("capability_id"),
            "goal_id": plan.get("goal_id"),
            "assigned_capability_id": plan.get("assigned_capability_id"),
            "runaway_selected_metric_id": plan.get("runaway_selected_metric_id"),
            "runaway_escalation_level_u64": plan.get("runaway_escalation_level_u64"),
            "runaway_env_overrides": plan.get("runaway_env_overrides"),
        }
    )


def build_decision_plan_from_selection(
    *,
    tick_u64: int,
    observation_report_hash: str,
    issue_bundle_hash: str,
    policy_hash: str,
    registry_hash: str,
    budgets_hash: str,
    registry: dict[str, Any],
    selection_receipt: dict[str, Any],
) -> dict[str, Any]:
    tie_break_path = list(selection_receipt.get("tie_break_path") or [])
    if not isinstance(tie_break_path, list):
        fail("SCHEMA_FAIL")
    action_kind = "NOOP"
    winner = selection_receipt.get("winner")
    plan: dict[str, Any] = {
        "schema_version": "omega_decision_plan_v1",
        "plan_id": "sha256:" + ("0" * 64),
        "tick_u64": int(tick_u64),
        "observation_report_hash": str(observation_report_hash),
        "issue_bundle_hash": str(issue_bundle_hash),
        "policy_hash": str(policy_hash),
        "registry_hash": str(registry_hash),
        "budgets_hash": str(budgets_hash),
        "action_kind": "NOOP",
        "tie_break_path": tie_break_path,
        "recompute_proof": {"inputs_hash": "sha256:" + ("0" * 64), "plan_hash": "sha256:" + ("0" * 64)},
    }
    if isinstance(winner, dict) and str(selection_receipt.get("outcome", "")) == "OK":
        campaign_id = str(winner.get("campaign_id", "")).strip()
        if campaign_id:
            # Resolve capability row for pack hash/verifier module.
            caps = registry.get("capabilities")
            if not isinstance(caps, list):
                fail("SCHEMA_FAIL")
            cap_row = None
            for row in caps:
                if isinstance(row, dict) and str(row.get("campaign_id")) == campaign_id:
                    cap_row = row
                    break
            if cap_row is None:
                fail("CAPABILITY_NOT_FOUND")
            campaign_pack_rel = str(cap_row.get("campaign_pack_rel"))
            action_kind = "RUN_CAMPAIGN"
            plan.update(
                {
                    "action_kind": action_kind,
                    "campaign_id": campaign_id,
                    "capability_id": str(cap_row.get("capability_id")),
                    "campaign_pack_hash": canon_hash_obj({"campaign_pack_rel": campaign_pack_rel}),
                    "expected_verifier_module": str(cap_row.get("verifier_module")),
                    "priority_q32": q32_obj(int(Q32_ONE)),
                }
            )

    plan["recompute_proof"] = {"inputs_hash": _decision_inputs_hash(plan), "plan_hash": "sha256:" + ("0" * 64)}
    no_id = dict(plan)
    no_id.pop("plan_id", None)
    plan_id = canon_hash_obj(no_id)
    plan["plan_id"] = plan_id
    plan["recompute_proof"] = {"inputs_hash": plan["recompute_proof"]["inputs_hash"], "plan_hash": plan_id}
    validate_schema(plan, "omega_decision_plan_v1")
    return plan


__all__ = [
    "J_prev_q32_from_metric_series",
    "J_q32_from_observation",
    "bid_market_enabled",
    "bootstrap_market_state",
    "build_bid_set_v1",
    "build_bid_v1",
    "build_decision_plan_from_selection",
    "load_bid_market_config",
    "load_latest_bid_market_state",
    "load_optional_bid_market_config",
    "resolve_bidder_params",
    "resolve_settlement_params",
    "select_winner",
    "settle_and_advance_market_state",
    "write_bid_market_state",
    "write_bid_selection_receipt",
    "write_bid_set_v1",
    "write_bid_settlement_receipt",
    "write_bid_v1",
]
