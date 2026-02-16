"""Restricted abstraction operator ISA for CAOE v1.2 proposer."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

base_dir = Path(__file__).resolve().parents[1]
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))

from sleep.operators.coarse_grain_merge_v1 import propose as propose_coarse_grain  # noqa: E402
from sleep.operators.efe_tune_v1_1 import propose as propose_efe_tune  # noqa: E402
from sleep.operators.latent_reify_v1 import propose as propose_latent_reify  # noqa: E402
from sleep.operators.render_canonicalize_phi_v1_1 import propose as propose_render_canon  # noqa: E402
from sleep.operators.stability_latent_detect_v1_1 import propose as propose_stability_latent  # noqa: E402
from sleep.operators.template_extract_v1 import propose as propose_template_extract  # noqa: E402
from sleep.operators.option_compile_v1_1 import propose as propose_option_compile_v1_1  # noqa: E402
from sleep.operators.rate_scale_repeat_option_v1_2 import propose as propose_rate_scale_repeat  # noqa: E402
from sleep.operators.temporal_denoise_phi_v1_2 import propose as propose_temporal_denoise  # noqa: E402
from sleep.operators.hysteresis_filter_v1_2 import propose as propose_hysteresis_filter  # noqa: E402
from sleep.synth.bounded_program_enumerator_v1 import enumerate_programs  # noqa: E402
from sleep.synth.degeneracy_v1 import depends_on  # noqa: E402

ABSOP_COARSE_GRAIN_MERGE_V1 = "ABSOP_COARSE_GRAIN_MERGE_V1"
ABSOP_LATENT_REIFY_V1 = "ABSOP_LATENT_REIFY_V1"
ABSOP_TEMPLATE_EXTRACT_V1 = "ABSOP_TEMPLATE_EXTRACT_V1"
ABSOP_OPTION_COMPILE_V1 = "ABSOP_OPTION_COMPILE_V1"
ABSOP_OPTION_COMPILE_V1_1 = "ABSOP_OPTION_COMPILE_V1_1"
ABSOP_STABILITY_LATENT_DETECT_V1_1 = "ABSOP_STABILITY_LATENT_DETECT_V1_1"
ABSOP_EFE_TUNE_V1_1 = "ABSOP_EFE_TUNE_V1_1"
ABSOP_RENDER_CANONICALIZE_PHI_V1_1 = "ABSOP_RENDER_CANONICALIZE_PHI_V1_1"
ABSOP_RATE_SCALE_REPEAT_OPTION_V1_2 = "ABSOP_RATE_SCALE_REPEAT_OPTION_V1_2"
ABSOP_TEMPORAL_DENOISE_PHI_V1_2 = "ABSOP_TEMPORAL_DENOISE_PHI_V1_2"
ABSOP_HYSTERESIS_FILTER_V1_2 = "ABSOP_HYSTERESIS_FILTER_V1_2"

ALLOWED_OP_IDS = {
    ABSOP_COARSE_GRAIN_MERGE_V1,
    ABSOP_LATENT_REIFY_V1,
    ABSOP_TEMPLATE_EXTRACT_V1,
    ABSOP_OPTION_COMPILE_V1,
    ABSOP_OPTION_COMPILE_V1_1,
    ABSOP_STABILITY_LATENT_DETECT_V1_1,
    ABSOP_EFE_TUNE_V1_1,
    ABSOP_RENDER_CANONICALIZE_PHI_V1_1,
    ABSOP_RATE_SCALE_REPEAT_OPTION_V1_2,
    ABSOP_TEMPORAL_DENOISE_PHI_V1_2,
    ABSOP_HYSTERESIS_FILTER_V1_2,
}


class AbsOpError(ValueError):
    pass


def operator_rankings(state: dict[str, Any]) -> dict[str, int]:
    weights = state.get("operator_weights") or {}
    items = sorted(weights.items(), key=lambda x: (-x[1], x[0]))
    return {op_id: idx for idx, (op_id, _w) in enumerate(items)}


def _is_quarantined(state: dict[str, Any], op_id: str, epoch_num: int) -> bool:
    until = state.get("operator_quarantine_until_epoch", {}).get(op_id, 0)
    return int(until) >= int(epoch_num)


def _propose_option_compile(
    anomaly_buffer: dict[str, Any],
    base_ontology: dict[str, Any],
    base_mech: dict[str, Any],
    proposer_state: dict[str, Any],
) -> list[dict[str, Any]]:
    if not proposer_state.get("allow_macro_ops", False):
        return []
    # Gated by macro stage enabled.
    if not proposer_state.get("macro_stage_enabled", False):
        return []
    complexity = base_ontology.get("complexity_limits", {})
    psi_max_ops = int(complexity.get("psi_max_ops", 0))
    max_constants = int(complexity.get("max_constants", 0))
    # Build a trivial psi program with constant outputs if possible.
    base_psi = base_ontology.get("lifting_psi")
    if not isinstance(base_psi, dict):
        return []
    inputs = base_psi.get("inputs", [])
    outputs = base_psi.get("outputs", [])
    programs = enumerate_programs(
        inputs=inputs,
        outputs=outputs,
        max_ops=psi_max_ops,
        max_constants=max_constants,
        limit=16,
    )
    filtered: list[dict[str, Any]] = []
    do_inputs = {item.get("name") for item in inputs if item.get("name")}
    for entry in programs:
        program = entry["program"]
        if not depends_on(program, set(do_inputs)):
            continue
        ops = program.get("ops") or []
        consts: dict[str, int] = {}
        psi_value_dep = False
        for op in ops:
            if not isinstance(op, dict):
                continue
            if op.get("op") == "CONST":
                dst = op.get("dst")
                args = op.get("args") or []
                if not dst or len(args) != 1 or not isinstance(args[0], dict):
                    continue
                if "int" in args[0]:
                    consts[dst] = int(args[0]["int"])
            if op.get("op") == "GET":
                dst = op.get("dst")
                args = op.get("args") or []
                if dst == "psi_0_value" and args and args[0] in do_inputs:
                    psi_value_dep = True
        psi_len = consts.get("psi_len")
        psi_0_type = consts.get("psi_0_type")
        psi_0_index = consts.get("psi_0_index", 0)
        if psi_len not in (1, 2, 3, 4):
            continue
        if psi_0_type != 1:
            continue
        if not isinstance(psi_0_index, int) or psi_0_index < 0 or psi_0_index >= 4:
            continue
        if not psi_value_dep:
            continue
        filtered.append(entry)
    if not filtered:
        return []
    program_entry = filtered[0]
    program = program_entry["program"]
    ontology_patch = {
        "format": "ontology_patch_v1_1",
        "schema_version": 1,
        "base_ontology_hash": anomaly_buffer.get("base_ontology_hash"),
        "ops": [
            {"op": "set_supports_macro_do", "value": True},
            {"op": "replace_psi", "psi": program},
        ],
        "claimed_obligations": {
            "requires_c_do": True,
            "requires_c_mdl": True,
            "requires_c_inv": True,
            "requires_c_anti": True,
        },
        "predicted_gains": {
            "delta_mdl_bits": 0,
            "delta_worst_case_success": 0.0,
            "delta_efficiency": 0.0,
        },
    }
    derivation = {
        "base_candidate_id": anomaly_buffer.get("identity_candidate_id", ""),
        "used_regime_ids": [
            item.get("regime_id") for item in anomaly_buffer.get("signals", {}).get("worst_regimes", [])
        ],
        "operator_internal_notes": {"stage": "macro_option_compile", "version": 1},
    }
    return [
        {
            "op_id": ABSOP_OPTION_COMPILE_V1,
            "ontology_patch": ontology_patch,
            "mech_diff": None,
            "program_blobs": {"programs/psi.bp": program_entry["bytes"]},
            "claimed_obligations": ontology_patch["claimed_obligations"],
            "predicted_gains": ontology_patch["predicted_gains"],
            "derivation": derivation,
        }
    ]


def propose_candidates(
    *,
    anomaly_buffer: dict[str, Any],
    base_ontology: dict[str, Any],
    base_mech: dict[str, Any],
    proposer_state: dict[str, Any],
    epoch_num: int,
) -> list[dict[str, Any]]:
    proposals: list[dict[str, Any]] = []

    if not _is_quarantined(proposer_state, ABSOP_COARSE_GRAIN_MERGE_V1, epoch_num):
        proposals.extend(propose_coarse_grain(anomaly_buffer, base_ontology, base_mech, proposer_state))
    if not _is_quarantined(proposer_state, ABSOP_STABILITY_LATENT_DETECT_V1_1, epoch_num):
        proposals.extend(propose_stability_latent(anomaly_buffer, base_ontology, base_mech, proposer_state))
    if not _is_quarantined(proposer_state, ABSOP_RENDER_CANONICALIZE_PHI_V1_1, epoch_num):
        proposals.extend(propose_render_canon(anomaly_buffer, base_ontology, base_mech, proposer_state))
    if not _is_quarantined(proposer_state, ABSOP_LATENT_REIFY_V1, epoch_num):
        proposals.extend(propose_latent_reify(anomaly_buffer, base_ontology, base_mech, proposer_state))
    if not _is_quarantined(proposer_state, ABSOP_TEMPLATE_EXTRACT_V1, epoch_num):
        proposals.extend(propose_template_extract(anomaly_buffer, base_ontology, base_mech, proposer_state))
    if not _is_quarantined(proposer_state, ABSOP_EFE_TUNE_V1_1, epoch_num):
        proposals.extend(propose_efe_tune(anomaly_buffer, base_ontology, base_mech, proposer_state))
    if not _is_quarantined(proposer_state, ABSOP_OPTION_COMPILE_V1, epoch_num):
        proposals.extend(_propose_option_compile(anomaly_buffer, base_ontology, base_mech, proposer_state))
    if not _is_quarantined(proposer_state, ABSOP_OPTION_COMPILE_V1_1, epoch_num):
        proposals.extend(propose_option_compile_v1_1(anomaly_buffer, base_ontology, base_mech, proposer_state))
    if not _is_quarantined(proposer_state, ABSOP_RATE_SCALE_REPEAT_OPTION_V1_2, epoch_num):
        proposals.extend(propose_rate_scale_repeat(anomaly_buffer, base_ontology, base_mech, proposer_state))
    if not _is_quarantined(proposer_state, ABSOP_TEMPORAL_DENOISE_PHI_V1_2, epoch_num):
        proposals.extend(propose_temporal_denoise(anomaly_buffer, base_ontology, base_mech, proposer_state))
    if not _is_quarantined(proposer_state, ABSOP_HYSTERESIS_FILTER_V1_2, epoch_num):
        proposals.extend(propose_hysteresis_filter(anomaly_buffer, base_ontology, base_mech, proposer_state))

    for proposal in proposals:
        op_id = proposal.get("op_id")
        if op_id not in ALLOWED_OP_IDS:
            raise AbsOpError("proposal op_id not allowed")
    return proposals


def validate_op_ids(proposals: list[dict[str, Any]]) -> None:
    for proposal in proposals:
        op_id = proposal.get("op_id")
        if op_id not in ALLOWED_OP_IDS:
            raise AbsOpError("proposal op_id not allowed")


def propose_candidates_with_stats(
    *,
    anomaly_buffer: dict[str, Any],
    base_ontology: dict[str, Any],
    base_mech: dict[str, Any],
    proposer_state: dict[str, Any],
    epoch_num: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    proposals: list[dict[str, Any]] = []
    counts_by_operator: dict[str, int] = {op_id: 0 for op_id in ALLOWED_OP_IDS}
    skipped_by_operator: dict[str, int] = {op_id: 0 for op_id in ALLOWED_OP_IDS}
    skip_reason_counts: dict[str, int] = {}

    def _record_skip(op_id: str, reason: str) -> None:
        skipped_by_operator[op_id] = skipped_by_operator.get(op_id, 0) + 1
        skip_reason_counts[reason] = skip_reason_counts.get(reason, 0) + 1

    if _is_quarantined(proposer_state, ABSOP_COARSE_GRAIN_MERGE_V1, epoch_num):
        _record_skip(ABSOP_COARSE_GRAIN_MERGE_V1, f"SKIP_QUARANTINE_{ABSOP_COARSE_GRAIN_MERGE_V1}")
    else:
        new = propose_coarse_grain(anomaly_buffer, base_ontology, base_mech, proposer_state)
        proposals.extend(new)
        counts_by_operator[ABSOP_COARSE_GRAIN_MERGE_V1] += len(new)

    if _is_quarantined(proposer_state, ABSOP_STABILITY_LATENT_DETECT_V1_1, epoch_num):
        _record_skip(ABSOP_STABILITY_LATENT_DETECT_V1_1, f"SKIP_QUARANTINE_{ABSOP_STABILITY_LATENT_DETECT_V1_1}")
    else:
        new = propose_stability_latent(anomaly_buffer, base_ontology, base_mech, proposer_state)
        proposals.extend(new)
        counts_by_operator[ABSOP_STABILITY_LATENT_DETECT_V1_1] += len(new)

    if _is_quarantined(proposer_state, ABSOP_RENDER_CANONICALIZE_PHI_V1_1, epoch_num):
        _record_skip(ABSOP_RENDER_CANONICALIZE_PHI_V1_1, f"SKIP_QUARANTINE_{ABSOP_RENDER_CANONICALIZE_PHI_V1_1}")
    else:
        new = propose_render_canon(anomaly_buffer, base_ontology, base_mech, proposer_state)
        proposals.extend(new)
        counts_by_operator[ABSOP_RENDER_CANONICALIZE_PHI_V1_1] += len(new)

    if _is_quarantined(proposer_state, ABSOP_LATENT_REIFY_V1, epoch_num):
        _record_skip(ABSOP_LATENT_REIFY_V1, f"SKIP_QUARANTINE_{ABSOP_LATENT_REIFY_V1}")
    elif base_ontology.get("supports_macro_do"):
        _record_skip(ABSOP_LATENT_REIFY_V1, "SKIP_LATENT_REIFY_MACRO_DO")
    else:
        new = propose_latent_reify(anomaly_buffer, base_ontology, base_mech, proposer_state)
        proposals.extend(new)
        counts_by_operator[ABSOP_LATENT_REIFY_V1] += len(new)

    if _is_quarantined(proposer_state, ABSOP_TEMPLATE_EXTRACT_V1, epoch_num):
        _record_skip(ABSOP_TEMPLATE_EXTRACT_V1, f"SKIP_QUARANTINE_{ABSOP_TEMPLATE_EXTRACT_V1}")
    else:
        new = propose_template_extract(anomaly_buffer, base_ontology, base_mech, proposer_state)
        proposals.extend(new)
        counts_by_operator[ABSOP_TEMPLATE_EXTRACT_V1] += len(new)

    if _is_quarantined(proposer_state, ABSOP_EFE_TUNE_V1_1, epoch_num):
        _record_skip(ABSOP_EFE_TUNE_V1_1, f"SKIP_QUARANTINE_{ABSOP_EFE_TUNE_V1_1}")
    else:
        new = propose_efe_tune(anomaly_buffer, base_ontology, base_mech, proposer_state)
        proposals.extend(new)
        counts_by_operator[ABSOP_EFE_TUNE_V1_1] += len(new)

    if _is_quarantined(proposer_state, ABSOP_OPTION_COMPILE_V1, epoch_num):
        _record_skip(ABSOP_OPTION_COMPILE_V1, f"SKIP_QUARANTINE_{ABSOP_OPTION_COMPILE_V1}")
    elif not proposer_state.get("allow_macro_ops", False):
        _record_skip(ABSOP_OPTION_COMPILE_V1, "SKIP_OPTION_COMPILE_MACRO_DISABLED")
    elif not proposer_state.get("macro_stage_enabled", False):
        _record_skip(ABSOP_OPTION_COMPILE_V1, "SKIP_OPTION_COMPILE_STAGE_DISABLED")
    else:
        new = _propose_option_compile(anomaly_buffer, base_ontology, base_mech, proposer_state)
        proposals.extend(new)
        counts_by_operator[ABSOP_OPTION_COMPILE_V1] += len(new)

    if _is_quarantined(proposer_state, ABSOP_OPTION_COMPILE_V1_1, epoch_num):
        _record_skip(ABSOP_OPTION_COMPILE_V1_1, f"SKIP_QUARANTINE_{ABSOP_OPTION_COMPILE_V1_1}")
    else:
        new = propose_option_compile_v1_1(anomaly_buffer, base_ontology, base_mech, proposer_state)
        proposals.extend(new)
        counts_by_operator[ABSOP_OPTION_COMPILE_V1_1] += len(new)

    if _is_quarantined(proposer_state, ABSOP_RATE_SCALE_REPEAT_OPTION_V1_2, epoch_num):
        _record_skip(ABSOP_RATE_SCALE_REPEAT_OPTION_V1_2, f"SKIP_QUARANTINE_{ABSOP_RATE_SCALE_REPEAT_OPTION_V1_2}")
    else:
        new = propose_rate_scale_repeat(anomaly_buffer, base_ontology, base_mech, proposer_state)
        proposals.extend(new)
        counts_by_operator[ABSOP_RATE_SCALE_REPEAT_OPTION_V1_2] += len(new)

    if _is_quarantined(proposer_state, ABSOP_TEMPORAL_DENOISE_PHI_V1_2, epoch_num):
        _record_skip(ABSOP_TEMPORAL_DENOISE_PHI_V1_2, f"SKIP_QUARANTINE_{ABSOP_TEMPORAL_DENOISE_PHI_V1_2}")
    else:
        new = propose_temporal_denoise(anomaly_buffer, base_ontology, base_mech, proposer_state)
        proposals.extend(new)
        counts_by_operator[ABSOP_TEMPORAL_DENOISE_PHI_V1_2] += len(new)

    if _is_quarantined(proposer_state, ABSOP_HYSTERESIS_FILTER_V1_2, epoch_num):
        _record_skip(ABSOP_HYSTERESIS_FILTER_V1_2, f"SKIP_QUARANTINE_{ABSOP_HYSTERESIS_FILTER_V1_2}")
    else:
        new = propose_hysteresis_filter(anomaly_buffer, base_ontology, base_mech, proposer_state)
        proposals.extend(new)
        counts_by_operator[ABSOP_HYSTERESIS_FILTER_V1_2] += len(new)

    for proposal in proposals:
        op_id = proposal.get("op_id")
        if op_id not in ALLOWED_OP_IDS:
            raise AbsOpError("proposal op_id not allowed")

    stats = {
        "counts_by_operator": counts_by_operator,
        "skipped_by_operator_counts": skipped_by_operator,
        "skip_reason_counts": skip_reason_counts,
    }
    return proposals, stats
