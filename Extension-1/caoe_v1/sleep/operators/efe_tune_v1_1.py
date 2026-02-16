"""ABSOP_EFE_TUNE_V1_1 operator implementation."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

base_dir = Path(__file__).resolve().parents[2]
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))

from artifacts.ids_v1 import mechanism_hash, ontology_hash  # noqa: E402

OP_ID = "ABSOP_EFE_TUNE_V1_1"
POLICY_PARAMS_MECH_ID = "ccai_x_policy_params_v1_1"


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


def _policy_mechanism(params: dict[str, int]) -> dict[str, Any]:
    return {
        "mechanism_id": POLICY_PARAMS_MECH_ID,
        "inputs": [],
        "outputs": [],
        "transition": _empty_transition(),
        "params": params,
    }


def _candidate_params(base_params: dict[str, int]) -> list[dict[str, int]]:
    ambiguity_weights = sorted({0, base_params.get("ambiguity_weight", 1), 2})
    complexity_weights = sorted({0, base_params.get("complexity_weight", 1), 1})
    exploration_weights = sorted({0, base_params.get("exploration_bonus_weight", 0), 1})
    horizon = int(base_params.get("horizon", 4))
    risk_weight = int(base_params.get("risk_weight", 1))

    params_list: list[dict[str, int]] = []
    horizon_values = sorted({max(1, horizon - 1), horizon, horizon + 2, 2, 6})
    for amb in ambiguity_weights:
        for comp in complexity_weights:
            for expl in exploration_weights:
                for hor in horizon_values:
                    params = {
                        "risk_weight": risk_weight,
                        "ambiguity_weight": int(amb),
                        "complexity_weight": int(comp),
                        "exploration_bonus_weight": int(expl),
                        "horizon": int(hor),
                    }
                    params_list.append(params)
    params_list = [p for p in params_list if p != base_params]
    params_list.sort(
        key=lambda p: (
            p["horizon"],
            p["ambiguity_weight"],
            p["complexity_weight"],
            p["exploration_bonus_weight"],
            p["risk_weight"],
        )
    )
    return params_list[:12]


def _predicted_gains(anomaly_buffer: dict[str, Any]) -> dict[str, Any]:
    global_sig = anomaly_buffer.get("signals", {}).get("global", {})
    wcs = float(global_sig.get("heldout_worst_case_success", 0.0))
    delta = 0.02 if wcs < 0.5 else 0.01
    return {
        "delta_mdl_bits": 0,
        "delta_worst_case_success": delta,
        "delta_efficiency": 0.0,
    }


def propose(
    anomaly_buffer: dict[str, Any],
    base_ontology: dict[str, Any],
    base_mech: dict[str, Any],
    proposer_state: dict[str, Any],
) -> list[dict[str, Any]]:
    base_hash = anomaly_buffer.get("base_ontology_hash") or ontology_hash(base_ontology)
    mech_hash = mechanism_hash(base_mech)
    gains = _predicted_gains(anomaly_buffer)

    base_params = _policy_params_from_mech(base_mech)
    param_grid = _candidate_params(base_params)
    if not param_grid:
        return []

    has_policy = any(
        mech.get("mechanism_id") == POLICY_PARAMS_MECH_ID for mech in (base_mech.get("mechanisms") or [])
    )
    op_kind = "replace_mechanism" if has_policy else "add_mechanism"

    ontology_patch = {
        "format": "ontology_patch_v1_1",
        "schema_version": 1,
        "base_ontology_hash": base_hash,
        "ops": [],
        "claimed_obligations": {
            "requires_c_do": bool(base_ontology.get("supports_macro_do", False)),
            "requires_c_mdl": True,
            "requires_c_inv": True,
            "requires_c_anti": True,
        },
        "predicted_gains": gains,
    }

    proposals: list[dict[str, Any]] = []
    for params in param_grid:
        mech_diff = {
            "format": "mechanism_registry_diff_v1_1",
            "schema_version": 1,
            "base_mech_hash": mech_hash,
            "ops": [
                {
                    "op": op_kind,
                    "mechanism": _policy_mechanism(params),
                }
            ],
        }
        derivation = {
            "base_candidate_id": anomaly_buffer.get("identity_candidate_id", ""),
            "used_regime_ids": [
                item.get("regime_id") for item in anomaly_buffer.get("signals", {}).get("worst_regimes", [])
            ],
            "operator_internal_notes": {
                "variant": "efe_tune",
                "policy_params": params,
            },
        }
        proposals.append(
            {
                "op_id": OP_ID,
                "ontology_patch": ontology_patch,
                "mech_diff": mech_diff,
                "program_blobs": {},
                "claimed_obligations": ontology_patch["claimed_obligations"],
                "predicted_gains": gains,
                "derivation": derivation,
            }
        )
    return proposals
