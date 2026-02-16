"""ABSOP_LATENT_REIFY_V1 operator implementation."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

base_dir = Path(__file__).resolve().parents[2]
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))

from artifacts.ids_v1 import mechanism_hash, ontology_hash  # noqa: E402
from sleep.synth.bounded_program_enumerator_v1 import enumerate_programs  # noqa: E402
from sleep.synth.guided_program_order_v1_2 import order_programs  # noqa: E402

OP_ID = "ABSOP_LATENT_REIFY_V1"


def _latent_names(base_ontology: dict[str, Any], count: int) -> list[str]:
    existing = {sym.get("name") for sym in base_ontology.get("symbols", []) if isinstance(sym, dict)}
    names: list[str] = []
    idx = 0
    while len(names) < count:
        name = f"latent_l{idx}"
        if name not in existing:
            names.append(name)
        idx += 1
    return names


def _predicted_gains(anomaly_buffer: dict[str, Any]) -> dict[str, Any]:
    # Heuristic: higher MDL payback if leakage sensitivity is high.
    leakage = anomaly_buffer.get("signals", {}).get("global", {}).get("leakage_sensitivity", 0.0)
    relabel = anomaly_buffer.get("signals", {}).get("global", {}).get("relabel_sensitivity", 0.0)
    score = int((float(leakage) + float(relabel)) * 100)
    return {
        "delta_mdl_bits": -max(1, score // 2),
        "delta_worst_case_success": min(0.2, score / 1000.0),
        "delta_efficiency": min(0.2, score / 1500.0),
    }


def propose(
    anomaly_buffer: dict[str, Any],
    base_ontology: dict[str, Any],
    base_mech: dict[str, Any],
    proposer_state: dict[str, Any],
) -> list[dict[str, Any]]:
    if base_ontology.get("supports_macro_do"):
        return []
    base_hash = anomaly_buffer.get("base_ontology_hash") or ontology_hash(base_ontology)
    mech_hash = mechanism_hash(base_mech)
    new_symbols = _latent_names(base_ontology, 2)
    gains = _predicted_gains(anomaly_buffer)

    base_phi = base_ontology.get("measurement_phi") or {}
    phi_inputs = base_phi.get("inputs", [])
    phi_outputs = list(base_phi.get("outputs", []))
    for name in new_symbols:
        phi_outputs.append({"name": name, "type": "bit"})

    complexity = base_ontology.get("complexity_limits", {})
    phi_max_ops = int(complexity.get("phi_max_ops", 0))
    max_constants = int(complexity.get("max_constants", 0))

    programs = enumerate_programs(
        inputs=phi_inputs,
        outputs=phi_outputs,
        max_ops=phi_max_ops,
        max_constants=max_constants,
        limit=16,
    )
    filtered: list[dict[str, Any]] = []
    for entry in programs:
        prog = entry["program"]
        ops = prog.get("ops") or []
        required = {name: False for name in new_symbols}
        for op in ops:
            if not isinstance(op, dict) or op.get("op") != "SLICE":
                continue
            args = op.get("args") or []
            if len(args) >= 1 and args[0] == "o_t":
                dst = op.get("dst")
                if dst in required:
                    required[dst] = True
        if all(required.values()):
            filtered.append(entry)
    programs = filtered
    if not programs:
        return []
    programs = order_programs(programs, anomaly_buffer=anomaly_buffer)
    program_entry = programs[0]

    ops = []
    for name in new_symbols:
        ops.append({"op": "add_symbol", "symbol": {"name": name, "type": "bit", "domain": {}}})
    ops.append({"op": "replace_phi", "phi": program_entry["program"]})

    ontology_patch = {
        "format": "ontology_patch_v1_1",
        "schema_version": 1,
        "base_ontology_hash": base_hash,
        "ops": ops,
        "claimed_obligations": {
            "requires_c_do": False,
            "requires_c_mdl": True,
            "requires_c_inv": True,
            "requires_c_anti": True,
        },
        "predicted_gains": gains,
    }

    mech_diff = None

    derivation = {
        "base_candidate_id": anomaly_buffer.get("identity_candidate_id", ""),
        "used_regime_ids": [
            item.get("regime_id") for item in anomaly_buffer.get("signals", {}).get("worst_regimes", [])
        ],
        "operator_internal_notes": {"variant": "latent_reify", "new_symbols": new_symbols},
    }

    return [
        {
            "op_id": OP_ID,
            "ontology_patch": ontology_patch,
            "mech_diff": mech_diff,
            "program_blobs": {"programs/phi.bp": program_entry["bytes"]},
            "claimed_obligations": ontology_patch["claimed_obligations"],
            "predicted_gains": gains,
            "derivation": derivation,
        }
    ]
