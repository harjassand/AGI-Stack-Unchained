"""ABSOP_STABILITY_LATENT_DETECT_V1_1 operator implementation."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

base_dir = Path(__file__).resolve().parents[2]
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))

from api_v1 import canonical_json_bytes  # noqa: E402
from artifacts.ids_v1 import ontology_hash  # noqa: E402

OP_ID = "ABSOP_STABILITY_LATENT_DETECT_V1_1"


def _o_t_decl(base_phi: dict[str, Any]) -> dict[str, Any] | None:
    for decl in base_phi.get("inputs") or []:
        if decl.get("name") == "o_t" and decl.get("type") == "bitvec":
            return decl
    return None


def _group_indices(max_width: int) -> list[list[int]]:
    max_idx = min(max_width, 20)
    groups: list[list[int]] = []
    for start in range(0, min(max_idx, 16), 4):
        group = list(range(start, min(start + 4, max_idx)))
        if len(group) == 4:
            groups.append(group)
    return groups


def _group_select_ops(name: str, indices: list[int]) -> list[dict[str, Any]]:
    ops: list[dict[str, Any]] = []
    cur_vars: list[str] = []
    diff_vars: list[str] = []
    for idx_pos, idx in enumerate(indices):
        cur = f"{name}_cur_{idx_pos}"
        prev = f"{name}_prev_{idx_pos}"
        diff = f"{name}_diff_{idx_pos}"
        ops.append({"dst": cur, "op": "SELECT_BIT", "args": ["o_t", idx]})
        ops.append({"dst": prev, "op": "SELECT_BIT", "args": ["o_t_minus_1", idx]})
        ops.append({"dst": diff, "op": "XOR", "args": [cur, prev]})
        cur_vars.append(cur)
        diff_vars.append(diff)
    group_bits = f"{name}_group_bits"
    argmin = f"{name}_argmin"
    ops.append({"dst": group_bits, "op": "CONCAT", "args": cur_vars})
    ops.append({"dst": argmin, "op": "ARGMIN", "args": diff_vars})
    ops.append({"dst": name, "op": "SELECT_BIT", "args": [group_bits, argmin]})
    return ops


def _predicted_gains(anomaly_buffer: dict[str, Any]) -> dict[str, Any]:
    global_sig = anomaly_buffer.get("signals", {}).get("global", {})
    wcs = float(global_sig.get("heldout_worst_case_success", 0.0))
    delta = 0.06 if wcs < 0.2 else 0.04
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
    base_phi = base_ontology.get("measurement_phi") or {}
    o_t_decl = _o_t_decl(base_phi)
    if o_t_decl is None:
        return []
    width = int(o_t_decl.get("width", 0))
    outputs = base_phi.get("outputs") or []
    if len(outputs) != 4:
        return []

    base_limits = base_ontology.get("complexity_limits") or {}
    phi_max_ops = int(base_limits.get("phi_max_ops", 0))
    base_history = int(base_limits.get("max_state_history", 1))
    if phi_max_ops <= 0:
        return []

    gains = _predicted_gains(anomaly_buffer)
    base_hash = anomaly_buffer.get("base_ontology_hash") or ontology_hash(base_ontology)

    inputs: list[dict[str, Any]] = []
    for decl in base_phi.get("inputs") or []:
        if decl.get("name") in {"o_t", "t"}:
            inputs.append(dict(decl))
    # Add history inputs.
    inputs.append({"name": "o_t_minus_1", "type": "bitvec", "width": width})

    groups = _group_indices(width)
    if len(groups) < len(outputs):
        return []

    ops: list[dict[str, Any]] = []
    for out_decl, group in zip(outputs, groups):
        name = out_decl.get("name")
        if not name:
            return []
        ops.extend(_group_select_ops(name, group))
    if phi_max_ops and len(ops) > phi_max_ops:
        return []

    program = {
        "format": "bounded_program_v1",
        "schema_version": 1,
        "inputs": inputs,
        "outputs": outputs,
        "ops": ops,
        "max_ops": phi_max_ops,
    }
    program_bytes = canonical_json_bytes(program)
    patch_ops: list[dict[str, Any]] = [{"op": "replace_phi", "phi": program}]
    if base_history < 2:
        new_limits = dict(base_limits)
        new_limits["max_state_history"] = 2
        patch_ops.append({"op": "set_complexity_limits", "limits": new_limits})
    ontology_patch = {
        "format": "ontology_patch_v1_1",
        "schema_version": 1,
        "base_ontology_hash": base_hash,
        "ops": patch_ops,
        "claimed_obligations": {
            "requires_c_do": bool(base_ontology.get("supports_macro_do", False)),
            "requires_c_mdl": True,
            "requires_c_inv": True,
            "requires_c_anti": True,
        },
        "predicted_gains": gains,
    }
    derivation = {
        "base_candidate_id": anomaly_buffer.get("identity_candidate_id", ""),
        "used_regime_ids": [
            item.get("regime_id") for item in anomaly_buffer.get("signals", {}).get("worst_regimes", [])
        ],
        "operator_internal_notes": {
            "variant": "stability_latent_detect_group_argmin",
            "groups": groups,
        },
    }
    return [
        {
            "op_id": OP_ID,
            "ontology_patch": ontology_patch,
            "mech_diff": None,
            "program_blobs": {"programs/phi.bp": program_bytes},
            "claimed_obligations": ontology_patch["claimed_obligations"],
            "predicted_gains": gains,
            "derivation": derivation,
        }
    ]
