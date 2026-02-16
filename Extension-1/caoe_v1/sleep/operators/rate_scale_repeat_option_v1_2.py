"""ABSOP_RATE_SCALE_REPEAT_OPTION_V1_2 operator implementation."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

base_dir = Path(__file__).resolve().parents[2]
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))

from artifacts.ids_v1 import mechanism_hash, ontology_hash  # noqa: E402

OP_ID = "ABSOP_RATE_SCALE_REPEAT_OPTION_V1_2"
REPEAT_ACTION_MECH_ID = "repeat_action_option_v1_2"
POLICY_PARAMS_MECH_ID = "ccai_x_policy_params_v1_1"
REPEAT_STEPS = [2, 3, 4, 6]
MAX_CANDIDATES = 24


def _action_set() -> list[tuple]:
    actions: list[tuple] = []
    for i in range(4):
        actions.append(("SET_X", i, 0))
        actions.append(("SET_X", i, 1))
    for j in range(16):
        actions.append(("TOGGLE_N", j))
    return actions


def _empty_transition() -> dict[str, Any]:
    return {
        "format": "bounded_program_v1",
        "schema_version": 1,
        "inputs": [],
        "outputs": [],
        "ops": [],
        "max_ops": 0,
    }


def _policy_params_from_mech(base_mech: dict[str, Any]) -> dict[str, int]:
    defaults = {
        "risk_weight": 1,
        "ambiguity_weight": 1,
        "complexity_weight": 1,
        "exploration_bonus_weight": 0,
        "horizon": 4,
    }
    for mech in base_mech.get("mechanisms") or []:
        if mech.get("mechanism_id") == POLICY_PARAMS_MECH_ID:
            params = mech.get("params") or {}
            for key in list(defaults.keys()):
                if isinstance(params.get(key), int):
                    defaults[key] = int(params[key])
            break
    return defaults


def _policy_params_mech(params: dict[str, int]) -> dict[str, Any]:
    return {
        "mechanism_id": POLICY_PARAMS_MECH_ID,
        "inputs": [],
        "outputs": [],
        "transition": _empty_transition(),
        "params": params,
    }


def _target_nuisance(anomaly_buffer: dict[str, Any]) -> bool:
    worst_regimes = anomaly_buffer.get("signals", {}).get("worst_regimes", [])
    for item in worst_regimes:
        if not isinstance(item, dict):
            continue
        rid = str(item.get("regime_id") or "")
        if rid.startswith("nuisance_k2") or rid.startswith("nuisance"):
            return True
    worst_families = anomaly_buffer.get("signals", {}).get("worst_families", [])
    for item in worst_families:
        if not isinstance(item, dict):
            continue
        fid = str(item.get("family_id") or "")
        if fid.startswith("nuisance_rate_scale") or fid.startswith("nuisance"):
            return True
    return False


def _predicted_gains(anomaly_buffer: dict[str, Any]) -> dict[str, Any]:
    global_sig = anomaly_buffer.get("signals", {}).get("global", {})
    wcs = float(global_sig.get("heldout_worst_case_success", 0.0))
    delta = 0.08 if wcs < 0.2 else 0.04
    return {
        "delta_mdl_bits": 0,
        "delta_worst_case_success": delta,
        "delta_efficiency": 0.0,
    }


def _select_action_repeat_pairs() -> list[tuple[int, int]]:
    actions = list(range(len(_action_set())))
    if not actions:
        return []
    selected: list[tuple[int, int]] = []
    for idx, action_id in enumerate(actions):
        repeat = REPEAT_STEPS[idx % len(REPEAT_STEPS)]
        selected.append((repeat, action_id))
    selected.sort(key=lambda x: (x[0], x[1]))
    return selected[:MAX_CANDIDATES]


def propose(
    anomaly_buffer: dict[str, Any],
    base_ontology: dict[str, Any],
    base_mech: dict[str, Any],
    proposer_state: dict[str, Any],
) -> list[dict[str, Any]]:
    dev_class = anomaly_buffer.get("dev_classification")
    if isinstance(dev_class, dict):
        if dev_class.get("unsolvable") or dev_class.get("needs_sequence_retry"):
            return []
    if not _target_nuisance(anomaly_buffer):
        return []

    base_hash = anomaly_buffer.get("base_ontology_hash") or ontology_hash(base_ontology)
    mech_hash = mechanism_hash(base_mech)
    gains = _predicted_gains(anomaly_buffer)
    isa_version = str(base_ontology.get("isa_version") or "caoe_absop_isa_v1_2")

    has_repeat = any(
        mech.get("mechanism_id") == REPEAT_ACTION_MECH_ID for mech in (base_mech.get("mechanisms") or [])
    )
    mech_op = "replace_mechanism" if has_repeat else "add_mechanism"
    base_params = _policy_params_from_mech(base_mech)
    tuned_params = dict(base_params)
    tuned_params["complexity_weight"] = 0
    tuned_params["horizon"] = max(int(tuned_params.get("horizon", 4)), 6)
    has_policy = any(
        mech.get("mechanism_id") == POLICY_PARAMS_MECH_ID for mech in (base_mech.get("mechanisms") or [])
    )
    policy_op = "replace_mechanism" if has_policy else "add_mechanism"

    proposals: list[dict[str, Any]] = []
    for repeat, action_id in _select_action_repeat_pairs():
        bias = (len(_action_set()) - int(action_id)) * 0.0001
        local_gains = dict(gains)
        local_gains["delta_worst_case_success"] = float(local_gains.get("delta_worst_case_success", 0.0)) + bias
        ontology_patch = {
            "format": "ontology_patch_v1_1",
            "schema_version": 1,
            "base_ontology_hash": base_hash,
            "isa_version": isa_version,
            "ops": [
                {"op": "set_supports_repeat_action_options", "value": True},
            ],
            "claimed_obligations": {
                "requires_c_do": bool(base_ontology.get("supports_macro_do", False)),
                "requires_c_mdl": True,
                "requires_c_inv": True,
                "requires_c_anti": True,
            },
            "predicted_gains": local_gains,
        }
        mech = {
            "mechanism_id": REPEAT_ACTION_MECH_ID,
            "inputs": [],
            "outputs": [],
            "transition": _empty_transition(),
            "params": {"action_id": int(action_id), "repeat_steps": int(repeat)},
        }
        mech_diff = {
            "format": "mechanism_registry_diff_v1_1",
            "schema_version": 1,
            "base_mech_hash": mech_hash,
            "ops": [
                {
                    "op": policy_op,
                    "mechanism": _policy_params_mech(tuned_params),
                },
                {
                    "op": mech_op,
                    "mechanism": mech,
                },
            ],
        }
        derivation = {
            "base_candidate_id": anomaly_buffer.get("identity_candidate_id", ""),
            "used_regime_ids": [
                item.get("regime_id") for item in anomaly_buffer.get("signals", {}).get("worst_regimes", [])
            ],
            "operator_internal_notes": {
                "variant": "repeat_action_option",
                "repeat_steps": int(repeat),
                "action_id": int(action_id),
            },
        }
        proposals.append(
            {
                "op_id": OP_ID,
                "ontology_patch": ontology_patch,
                "mech_diff": mech_diff,
                "program_blobs": {},
                "claimed_obligations": ontology_patch["claimed_obligations"],
                "predicted_gains": local_gains,
                "derivation": derivation,
            }
        )

    return proposals
