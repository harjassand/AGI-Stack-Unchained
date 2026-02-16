"""Proposer state storage for CAOE v1."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

base_dir = Path(__file__).resolve().parents[1]
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))

from api_v1 import atomic_write_json, load_json  # noqa: E402
from sleep.absop_isa_v1_2 import ALLOWED_OP_IDS  # noqa: E402

STATE_FILENAME = "proposer_state.json"


def _validate_history_entry(entry: dict[str, Any]) -> None:
    required = {
        "epoch": int,
        "selected_candidate_id": str,
        "selected_op_id": str,
        "decision": str,
        "worst_case_success": (int, float),
        "mdl_bits": (int, float),
        "anti_pass": bool,
        "do_pass": bool,
    }
    for key, typ in required.items():
        if key not in entry:
            raise ValueError(f"history entry missing {key}")
        if not isinstance(entry[key], typ):
            raise ValueError(f"history entry {key} invalid type")
    if entry["decision"] not in {"PASS", "FAIL", "NONE"}:
        raise ValueError("history entry decision invalid")
    if "any_c_anti_fail" in entry and not isinstance(entry["any_c_anti_fail"], bool):
        raise ValueError("history entry any_c_anti_fail invalid")
    if "had_any_pass" in entry and not isinstance(entry["had_any_pass"], bool):
        raise ValueError("history entry had_any_pass invalid")
    if "best_pass_wcs" in entry and not isinstance(entry["best_pass_wcs"], (int, float)):
        raise ValueError("history entry best_pass_wcs invalid")


def validate_state(state: dict[str, Any], op_ids: list[str] | None = None) -> None:
    if state.get("format") != "caoe_proposer_state_v1":
        raise ValueError("state format invalid")
    if state.get("schema_version") != 1:
        raise ValueError("state schema_version invalid")
    if not isinstance(state.get("current_epoch"), int) or state["current_epoch"] < 0:
        raise ValueError("state current_epoch invalid")
    if not isinstance(state.get("macro_stage_enabled"), bool):
        raise ValueError("state macro_stage_enabled invalid")
    if "allow_macro_ops" in state and not isinstance(state.get("allow_macro_ops"), bool):
        raise ValueError("state allow_macro_ops invalid")
    if "retest_candidate_id" in state and not isinstance(state.get("retest_candidate_id"), str):
        raise ValueError("state retest_candidate_id invalid")
    if "retest_candidate_op_id" in state and not isinstance(state.get("retest_candidate_op_id"), str):
        raise ValueError("state retest_candidate_op_id invalid")
    if "retest_pending" in state and not isinstance(state.get("retest_pending"), bool):
        raise ValueError("state retest_pending invalid")
    weights = state.get("operator_weights")
    quarantine = state.get("operator_quarantine_until_epoch")
    if not isinstance(weights, dict) or not isinstance(quarantine, dict):
        raise ValueError("state operator maps invalid")
    if op_ids is None:
        op_ids = sorted(ALLOWED_OP_IDS)
    for op_id in op_ids:
        if op_id not in weights or op_id not in quarantine:
            raise ValueError("state missing operator entry")
        if not isinstance(weights[op_id], int):
            raise ValueError("state operator weight invalid")
        if not isinstance(quarantine[op_id], int):
            raise ValueError("state operator quarantine invalid")
    recent = state.get("recent_anomaly_regimes")
    if not isinstance(recent, list):
        raise ValueError("state recent_anomaly_regimes invalid")
    if len(recent) > 64:
        raise ValueError("state recent_anomaly_regimes too long")
    for item in recent:
        if not isinstance(item, str):
            raise ValueError("state recent_anomaly_regimes item invalid")
    history = state.get("history")
    if not isinstance(history, list):
        raise ValueError("state history invalid")
    if len(history) > 50:
        raise ValueError("state history too long")
    for entry in history:
        if not isinstance(entry, dict):
            raise ValueError("state history entry invalid")
        _validate_history_entry(entry)


def default_state(op_ids: list[str] | None = None) -> dict[str, Any]:
    if op_ids is None:
        op_ids = sorted(ALLOWED_OP_IDS)
    weights = {op_id: 1000 for op_id in op_ids}
    quarantine = {op_id: 0 for op_id in op_ids}
    return {
        "format": "caoe_proposer_state_v1",
        "schema_version": 1,
        "current_epoch": 0,
        "operator_weights": weights,
        "operator_quarantine_until_epoch": quarantine,
        "recent_anomaly_regimes": [],
        "history": [],
        "macro_stage_enabled": False,
        "allow_macro_ops": False,
        "retest_candidate_id": "none",
        "retest_candidate_op_id": "none",
        "retest_pending": False,
    }


def load_state(state_dir: str | Path, op_ids: list[str] | None = None) -> dict[str, Any]:
    state_dir = Path(state_dir)
    state_path = state_dir / STATE_FILENAME
    if not state_path.exists():
        state = default_state(op_ids)
        atomic_write_json(state_path, state)
        return state
    state = load_json(state_path)
    if not isinstance(state, dict):
        raise ValueError("state file invalid")
    defaults = default_state(op_ids)
    for key, value in defaults.items():
        if key not in state:
            state[key] = value
    # Merge any newly added operator IDs into existing state maps.
    weights = state.get("operator_weights")
    quarantine = state.get("operator_quarantine_until_epoch")
    if isinstance(weights, dict) and isinstance(quarantine, dict):
        for op_id, val in (defaults.get("operator_weights") or {}).items():
            if op_id not in weights:
                weights[op_id] = val
        for op_id, val in (defaults.get("operator_quarantine_until_epoch") or {}).items():
            if op_id not in quarantine:
                quarantine[op_id] = val
    validate_state(state, op_ids)
    return state


def save_state(state_dir: str | Path, state: dict[str, Any]) -> None:
    state_dir = Path(state_dir)
    state_path = state_dir / STATE_FILENAME
    validate_state(state)
    atomic_write_json(state_path, state)
