"""ABSOP_RENDER_CANONICALIZE_PHI_V1_1 operator implementation."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

base_dir = Path(__file__).resolve().parents[2]
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))

from artifacts.ids_v1 import ontology_hash  # noqa: E402
from ontology_ops.phi_render_canonicalize_v1_1 import build_phi_program  # noqa: E402

OP_ID = "ABSOP_RENDER_CANONICALIZE_PHI_V1_1"


def _o_t_decl(base_phi: dict[str, Any]) -> dict[str, Any] | None:
    for decl in base_phi.get("inputs") or []:
        if decl.get("name") == "o_t" and decl.get("type") == "bitvec":
            return decl
    return None


def _outputs_ok(outputs: list[dict[str, Any]]) -> bool:
    if not outputs:
        return False
    for decl in outputs:
        if decl.get("type") != "bit":
            return False
    return True


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
    if width <= 0:
        return []
    outputs = base_phi.get("outputs") or []
    if not _outputs_ok(outputs):
        return []

    base_limits = base_ontology.get("complexity_limits") or {}
    phi_max_ops = int(base_limits.get("phi_max_ops", 0))
    if phi_max_ops <= 0:
        return []

    max_obs_dims = min(20, width)
    if max_obs_dims <= 0:
        return []

    gains = _predicted_gains(anomaly_buffer)
    base_hash = anomaly_buffer.get("base_ontology_hash") or ontology_hash(base_ontology)
    proposals: list[dict[str, Any]] = []

    variants = [
        (2, 0, "infer", "all"),
        (4, 0, "infer", "all"),
        (6, 0, "infer", "all"),
        (8, 0, "infer", "all"),
        (2, 1, "mask", "set"),
        (4, 1, "mask", "set"),
        (6, 1, "mask", "toggle"),
        (8, 1, "mask", "toggle"),
    ]
    for probe_k, delta_thr, mask_mode, pattern in variants:
        try:
            program, program_bytes = build_phi_program(
                base_phi,
                probe_steps_k=probe_k,
                delta_threshold=delta_thr,
                max_obs_dims=max_obs_dims,
                mask_mode=mask_mode,
                pattern=pattern,
                phi_max_ops=phi_max_ops,
            )
        except ValueError:
            continue
        ontology_patch = {
            "format": "ontology_patch_v1_1",
            "schema_version": 1,
            "base_ontology_hash": base_hash,
            "ops": [{"op": "replace_phi", "phi": program}],
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
                "variant": "render_canonicalize_phi",
                "probe_steps_k": probe_k,
                "delta_threshold": delta_thr,
                "mask_mode": mask_mode,
                "pattern": pattern,
                "max_obs_dims": max_obs_dims,
            },
        }
        proposals.append(
            {
                "op_id": OP_ID,
                "ontology_patch": ontology_patch,
                "mech_diff": None,
                "program_blobs": {"programs/phi.bp": program_bytes},
                "claimed_obligations": ontology_patch["claimed_obligations"],
                "predicted_gains": gains,
                "derivation": derivation,
            }
        )
    return proposals
