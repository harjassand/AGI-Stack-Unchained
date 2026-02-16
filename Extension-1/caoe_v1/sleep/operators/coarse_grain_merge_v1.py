"""ABSOP_COARSE_GRAIN_MERGE_V1 operator implementation."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

base_dir = Path(__file__).resolve().parents[2]
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))

from api_v1 import canonical_json_bytes  # noqa: E402
from artifacts.ids_v1 import ontology_hash  # noqa: E402
from sleep.synth.bounded_program_enumerator_v1 import enumerate_programs  # noqa: E402
from sleep.synth.degeneracy_v1 import is_degenerate_phi  # noqa: E402
from sleep.synth.guided_program_order_v1_2 import order_programs  # noqa: E402

OP_ID = "ABSOP_COARSE_GRAIN_MERGE_V1"


def _heuristic_score(anomaly_buffer: dict[str, Any]) -> int:
    score = 0
    for item in anomaly_buffer.get("signals", {}).get("worst_regimes", []):
        try:
            success = float(item.get("success", 0.0))
        except (TypeError, ValueError):
            success = 0.0
        score += int((1.0 - success) * 1000)
    return max(score, 0)


def _predicted_gains(score: int) -> dict[str, Any]:
    return {
        "delta_mdl_bits": -int(score // 50),
        "delta_worst_case_success": min(0.5, score / 10000.0),
        "delta_efficiency": min(0.5, score / 20000.0),
    }


def propose(
    anomaly_buffer: dict[str, Any],
    base_ontology: dict[str, Any],
    base_mech: dict[str, Any],
    proposer_state: dict[str, Any],
) -> list[dict[str, Any]]:
    base_hash = anomaly_buffer.get("base_ontology_hash") or ontology_hash(base_ontology)
    worst_regimes = anomaly_buffer.get("signals", {}).get("worst_regimes", [])
    used_regime_ids = [item.get("regime_id") for item in worst_regimes if isinstance(item, dict)]
    score = _heuristic_score(anomaly_buffer)
    gains = _predicted_gains(score)

    complexity = base_ontology.get("complexity_limits", {})
    phi_max_ops = int(complexity.get("phi_max_ops", 0))
    max_constants = int(complexity.get("max_constants", 0))

    base_phi = base_ontology.get("measurement_phi") or {}
    phi_inputs = base_phi.get("inputs", [])
    phi_outputs = base_phi.get("outputs", [])
    allowed_inputs = [item.get("name") for item in phi_inputs if item.get("name") in {"o_t", "t"}]

    def _phi_candidates_x4() -> list[dict[str, Any]]:
        out_names = [out.get("name") for out in phi_outputs]
        if len(out_names) != 4 or set(out_names) != {"x0", "x1", "x2", "x3"}:
            return []
        bitvec_inputs = [
            inp
            for inp in phi_inputs
            if inp.get("name") == "o_t" and inp.get("type") == "bitvec"
        ]
        if not bitvec_inputs:
            return []
        width = int(bitvec_inputs[0].get("width", 0))
        max_index = max(0, min(width, 20))
        if max_index < 4:
            return []

        index_sets: list[tuple[int, int, int, int]] = []
        for start in range(0, max_index, 4):
            if start + 3 < max_index:
                index_sets.append((start, start + 1, start + 2, start + 3))
        base_perm = [(0, 1, 2, 3), (1, 0, 2, 3), (2, 3, 0, 1), (3, 2, 1, 0)]
        for tup in base_perm:
            if all(idx < max_index for idx in tup) and tup not in index_sets:
                index_sets.append(tup)

        mask_patterns = [0, 1, 2, 4, 8, 15]
        candidates: list[dict[str, Any]] = []
        for tup in index_sets:
            for mask in mask_patterns:
                ops: list[dict[str, Any]] = []
                for out_idx, out_name in enumerate(out_names):
                    idx = tup[out_idx]
                    if mask & (1 << out_idx):
                        tmp = f"{out_name}_slice"
                        ops.append({"dst": tmp, "op": "SLICE", "args": ["o_t", idx, idx + 1]})
                        ops.append({"dst": out_name, "op": "XOR", "args": [tmp, {"bit": 1}]})
                    else:
                        ops.append({"dst": out_name, "op": "SLICE", "args": ["o_t", idx, idx + 1]})
                if len(ops) > phi_max_ops:
                    continue
                program = {
                    "format": "bounded_program_v1",
                    "schema_version": 1,
                    "inputs": phi_inputs,
                    "outputs": phi_outputs,
                    "ops": ops,
                    "max_ops": phi_max_ops,
                }
                data = canonical_json_bytes(program)
                candidates.append(
                    {
                        "program": program,
                        "bytes": data,
                        "meta": {
                            "uses_inputs": ["o_t"],
                            "has_const": False,
                            "all_const": False,
                            "op_count": len(ops),
                        },
                        "distinct_slices": len(set(tup)),
                    }
                )
        candidates = order_programs(candidates, anomaly_buffer=anomaly_buffer)
        return candidates[:16]

    phi_programs = _phi_candidates_x4()
    if not phi_programs:
        phi_programs = enumerate_programs(
            inputs=phi_inputs,
            outputs=phi_outputs,
            max_ops=phi_max_ops,
            max_constants=max_constants,
            allowed_inputs=allowed_inputs,
            limit=16,
        )
        phi_programs = [entry for entry in phi_programs if not is_degenerate_phi(entry["program"])]
        phi_programs = order_programs(phi_programs, anomaly_buffer=anomaly_buffer)
        phi_programs = phi_programs[:4]

    proposals: list[dict[str, Any]] = []
    for idx, entry in enumerate(phi_programs):
        phi_program = entry["program"]
        ontology_patch = {
            "format": "ontology_patch_v1_1",
            "schema_version": 1,
            "base_ontology_hash": base_hash,
            "ops": [
                {"op": "replace_phi", "phi": phi_program},
            ],
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
            "used_regime_ids": used_regime_ids,
            "operator_internal_notes": {"variant": "phi_only", "rank": idx, "heuristic_score": score},
        }
        proposals.append(
            {
                "op_id": OP_ID,
                "ontology_patch": ontology_patch,
                "mech_diff": None,
                "program_blobs": {"programs/phi.bp": entry["bytes"]},
                "claimed_obligations": ontology_patch["claimed_obligations"],
                "predicted_gains": gains,
                "derivation": derivation,
            }
        )

    return proposals
