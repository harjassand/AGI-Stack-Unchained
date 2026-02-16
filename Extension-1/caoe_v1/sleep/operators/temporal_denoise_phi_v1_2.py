"""ABSOP_TEMPORAL_DENOISE_PHI_V1_2 operator implementation."""

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

OP_ID = "ABSOP_TEMPORAL_DENOISE_PHI_V1_2"


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


def _outputs_ok(outputs: list[dict[str, Any]]) -> bool:
    if not outputs:
        return False
    for decl in outputs:
        if decl.get("type") != "bit":
            return False
    return True


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


def _select_variants(signature: dict[str, Any], width: int) -> list[dict[str, Any]]:
    ranked = _score_indices(signature, width)
    if not ranked:
        ranked = list(range(width))
    top_single = ranked[:4] if len(ranked) >= 4 else ranked
    variants: list[dict[str, Any]] = []
    for idx in top_single:
        variants.append({"kind": "single", "indices": [int(idx)]})

    pair_pool = ranked[:8] if len(ranked) >= 8 else ranked
    pair_scores: list[tuple[float, tuple[int, int]]] = []
    score_map = {idx: (len(ranked) - i) for i, idx in enumerate(ranked)}
    for a, b in combinations(pair_pool, 2):
        score = score_map.get(a, 0) + score_map.get(b, 0)
        pair_scores.append((score, (int(a), int(b))))
    pair_scores.sort(key=lambda item: (-item[0], item[1]))
    for _, pair in pair_scores[:4]:
        variants.append({"kind": "pair", "indices": [pair[0], pair[1]]})

    bundle_pool = ranked[:8] if len(ranked) >= 8 else ranked
    bundle_scores: list[tuple[float, tuple[int, int, int, int]]] = []
    if len(bundle_pool) >= 4:
        for combo in combinations(bundle_pool, 4):
            score = sum(score_map.get(idx, 0) for idx in combo)
            bundle_scores.append((score, tuple(int(idx) for idx in combo)))
        bundle_scores.sort(key=lambda item: (-item[0], item[1]))
        for _, bundle in bundle_scores[:4]:
            variants.append({"kind": "bundle", "indices": list(bundle)})

    return variants


def _input_decls(base_phi: dict[str, Any], width: int, current_name: str) -> list[dict[str, Any]]:
    inputs = [dict(decl) for decl in (base_phi.get("inputs") or []) if isinstance(decl, dict)]
    if not any(decl.get("name") == current_name for decl in inputs):
        inputs.append({"name": current_name, "type": "bitvec", "width": width})
    if not any(decl.get("name") == "o_t_minus_1" for decl in inputs):
        inputs.append({"name": "o_t_minus_1", "type": "bitvec", "width": width})
    return inputs


def _mapped_indices(indices: list[int], outputs_len: int, width: int, mode: str) -> list[int]:
    if outputs_len <= 0:
        return []
    if mode == "reverse":
        base = list(reversed(indices))
    else:
        base = list(indices)
    if not base:
        base = list(range(outputs_len))
    mapped: list[int] = []
    if mode == "mixed":
        fallback = [i % max(width, 1) for i in range(outputs_len)]
        for idx in range(outputs_len):
            if idx < len(base):
                mapped.append(base[idx] % max(width, 1))
            else:
                mapped.append(fallback[idx])
    else:
        for idx in range(outputs_len):
            mapped.append(base[idx % len(base)] % max(width, 1))
    return mapped


def _build_program(
    *,
    base_phi: dict[str, Any],
    outputs: list[dict[str, Any]],
    width: int,
    indices: list[int],
    mode: str,
    phi_max_ops: int,
    current_name: str,
) -> tuple[dict[str, Any], bytes] | None:
    inputs = _input_decls(base_phi, width, current_name)
    ops: list[dict[str, Any]] = []
    mapped = _mapped_indices(indices, len(outputs), width, mode)
    for out_idx, out_decl in enumerate(outputs):
        out_name = out_decl.get("name")
        if not out_name:
            return None
        idx = mapped[out_idx]
        if mode == "mixed" and out_idx >= len(indices):
            ops.append({"dst": out_name, "op": "SELECT_BIT", "args": [current_name, idx]})
        else:
            cur = f"{out_name}_cur"
            prev = f"{out_name}_prev"
            ops.append({"dst": cur, "op": "SELECT_BIT", "args": [current_name, idx]})
            ops.append({"dst": prev, "op": "SELECT_BIT", "args": ["o_t_minus_1", idx]})
            ops.append({"dst": out_name, "op": "DEBOUNCE2", "args": [cur, prev]})
    if phi_max_ops and len(ops) > phi_max_ops:
        return None
    program = {
        "format": "bounded_program_v1",
        "schema_version": 1,
        "inputs": inputs,
        "outputs": outputs,
        "ops": ops,
        "max_ops": phi_max_ops,
    }
    return program, canonical_json_bytes(program)


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
    outputs = base_phi.get("outputs") or []
    if width <= 0 or not _outputs_ok(outputs):
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

    gains = _predicted_gains(anomaly_buffer)
    base_hash = anomaly_buffer.get("base_ontology_hash") or ontology_hash(base_ontology)
    isa_version = str(base_ontology.get("isa_version") or "caoe_absop_isa_v1_2")

    variants = _select_variants(signature, width)
    if not variants:
        return []

    proposals: list[dict[str, Any]] = []
    for variant_idx, variant in enumerate(variants):
        indices = variant["indices"]
        kind = variant["kind"]
        built = _build_program(
            base_phi=base_phi,
            outputs=outputs,
            width=width,
            indices=indices,
            mode="full",
            phi_max_ops=phi_max_ops,
            current_name=current_name,
        )
        if built is None:
            continue
        program, program_bytes = built
        patch_ops: list[dict[str, Any]] = [
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
                "variant": "temporal_denoise",
                "kind": kind,
                "indices": indices,
                "mode": "full",
                "rank": variant_idx,
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
