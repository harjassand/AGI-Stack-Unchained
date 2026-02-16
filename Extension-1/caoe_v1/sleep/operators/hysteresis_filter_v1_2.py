"""ABSOP_HYSTERESIS_FILTER_V1_2 operator implementation."""

from __future__ import annotations

import sys
from itertools import combinations
from pathlib import Path
from typing import Any

base_dir = Path(__file__).resolve().parents[2]
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))

from api_v1 import canonical_json_bytes  # noqa: E402
from artifacts.ids_v1 import ontology_hash  # noqa: E402

OP_ID = "ABSOP_HYSTERESIS_FILTER_V1_2"


def _o_t_decl(base_phi: dict[str, Any]) -> dict[str, Any] | None:
    inputs = base_phi.get("inputs") or []
    for decl in inputs:
        if decl.get("type") != "bitvec":
            continue
        name = decl.get("name")
        if isinstance(name, str) and (name == "o_t" or name.startswith("o_t_canon_")):
            return decl
    for decl in inputs:
        if decl.get("type") != "bitvec":
            continue
        name = decl.get("name")
        if isinstance(name, str):
            return decl
    return None


def _score_indices(signature: dict[str, Any], width: int) -> list[int]:
    scores = {idx: 0.0 for idx in range(width)}
    action_map = signature.get("action_conditioned_effect_map") or {}
    for entry in action_map.values():
        if not isinstance(entry, dict):
            continue
        n = float(entry.get("n", 1.0))
        for idx in entry.get("changed_indices") or []:
            if isinstance(idx, int) and 0 <= idx < width:
                scores[idx] += n
    flip_rates = (signature.get("flip_rate_summary") or {}).get("per_index_flip_rate") or {}
    for idx, rate in flip_rates.items():
        try:
            idx_int = int(idx)
            rate_val = float(rate)
        except (TypeError, ValueError):
            continue
        if 0 <= idx_int < width:
            scores[idx_int] -= rate_val
    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return [idx for idx, _score in ranked]


def _select_variants(signature: dict[str, Any], width: int) -> list[list[int]]:
    ranked = _score_indices(signature, width)
    if not ranked:
        ranked = list(range(width))
    singles = ranked[:8] if len(ranked) >= 8 else ranked
    variants: list[list[int]] = [[int(idx)] for idx in singles]

    pair_pool = ranked[:8] if len(ranked) >= 8 else ranked
    score_map = {idx: (len(ranked) - i) for i, idx in enumerate(ranked)}
    pair_scores: list[tuple[float, tuple[int, int]]] = []
    for a, b in combinations(pair_pool, 2):
        score = score_map.get(a, 0) + score_map.get(b, 0)
        pair_scores.append((score, (int(a), int(b))))
    pair_scores.sort(key=lambda item: (-item[0], item[1]))
    for _, pair in pair_scores[:8]:
        variants.append([pair[0], pair[1]])

    if len(pair_pool) >= 4:
        bundle_scores: list[tuple[float, tuple[int, int, int, int]]] = []
        for combo in combinations(pair_pool, 4):
            score = sum(score_map.get(idx, 0) for idx in combo)
            bundle_scores.append((score, tuple(int(idx) for idx in combo)))
        bundle_scores.sort(key=lambda item: (-item[0], item[1]))
        for _, bundle in bundle_scores[:8]:
            variants.append(list(bundle))
    return variants


def _unique_names(base_symbols: set[str], indices: list[int]) -> list[str] | None:
    names: list[str] = []
    used = set(base_symbols)
    for idx in indices:
        base = f"hyst_{idx}"
        name = base
        if name in used:
            name = f"{base}_v1"
        if name in used:
            return None
        used.add(name)
        names.append(name)
    return names


def _input_decls(base_phi: dict[str, Any], width: int, current_name: str) -> list[dict[str, Any]]:
    inputs = [dict(decl) for decl in (base_phi.get("inputs") or []) if isinstance(decl, dict)]
    if not any(decl.get("name") == current_name for decl in inputs):
        inputs.append({"name": current_name, "type": "bitvec", "width": width})
    if not any(decl.get("name") == "o_t_minus_1" for decl in inputs):
        inputs.append({"name": "o_t_minus_1", "type": "bitvec", "width": width})
    return inputs


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
    dev_class = anomaly_buffer.get("dev_classification")
    if isinstance(dev_class, dict):
        if dev_class.get("unsolvable") or dev_class.get("needs_sequence_retry"):
            return []
    base_phi = base_ontology.get("measurement_phi") or {}
    o_t_decl = _o_t_decl(base_phi)
    if o_t_decl is None:
        return []
    width = int(o_t_decl.get("width", 0))
    current_name = str(o_t_decl.get("name") or "o_t")
    if width <= 0:
        return []

    signatures = anomaly_buffer.get("failure_signatures") or {}
    signature = signatures.get("nuisance_k2_00")
    if not isinstance(signature, dict) and signatures:
        signature = signatures.get(sorted(signatures.keys())[0])
    if not isinstance(signature, dict):
        return []
    sig_width = int(signature.get("obs_width", 0))
    if current_name.startswith("o_t_canon_"):
        if sig_width <= 0:
            return []
        current_name = "o_t"
        width = sig_width

    complexity = base_ontology.get("complexity_limits") or {}
    phi_max_ops = int(complexity.get("phi_max_ops", 0))
    if phi_max_ops <= 0:
        return []

    base_hash = anomaly_buffer.get("base_ontology_hash") or ontology_hash(base_ontology)
    isa_version = str(base_ontology.get("isa_version") or "caoe_absop_isa_v1_2")
    gains = _predicted_gains(anomaly_buffer)

    base_outputs = [dict(out) for out in (base_phi.get("outputs") or []) if isinstance(out, dict)]
    base_symbols = {sym.get("name") for sym in base_ontology.get("symbols") or [] if isinstance(sym, dict)}
    if any(name is None for name in base_symbols):
        base_symbols = {name for name in base_symbols if name}

    variants = _select_variants(signature, width)
    proposals: list[dict[str, Any]] = []
    for rank, indices in enumerate(variants):
        names = _unique_names(base_symbols, indices)
        if names is None:
            continue
        if len(base_symbols) + len(names) > 12:
            continue
        inputs = _input_decls(base_phi, width, current_name)
        outputs = list(base_outputs) + [{"name": name, "type": "bit"} for name in names]
        ops = [dict(op) for op in (base_phi.get("ops") or []) if isinstance(op, dict)]
        for idx, name in zip(indices, names):
            cur = f"{name}_cur"
            prev = f"{name}_prev"
            ops.append({"dst": cur, "op": "SELECT_BIT", "args": [current_name, int(idx)]})
            ops.append({"dst": prev, "op": "SELECT_BIT", "args": ["o_t_minus_1", int(idx)]})
            ops.append({"dst": name, "op": "DEBOUNCE2", "args": [cur, prev]})
        if phi_max_ops and len(ops) > phi_max_ops:
            continue
        program = {
            "format": "bounded_program_v1",
            "schema_version": 1,
            "inputs": inputs,
            "outputs": outputs,
            "ops": ops,
            "max_ops": phi_max_ops,
        }
        program_bytes = canonical_json_bytes(program)
        patch_ops: list[dict[str, Any]] = [
            *[{"op": "add_symbol", "symbol": {"name": name, "type": "bit", "domain": {}}} for name in names],
            {"op": "replace_phi", "phi": program},
        ]
        if int(complexity.get("max_state_history", 1)) != 2:
            new_limits = dict(complexity)
            new_limits["max_state_history"] = 2
            patch_ops.append({"op": "set_complexity_limits", "limits": new_limits})
        ontology_patch = {
            "format": "ontology_patch_v1_1",
            "schema_version": 1,
            "base_ontology_hash": base_hash,
            "isa_version": isa_version,
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
                "variant": "hysteresis_filter",
                "indices": indices,
                "symbols": names,
                "rank": rank,
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
