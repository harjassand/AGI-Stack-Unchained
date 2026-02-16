"""Patch synthesizer for CAOE v1 proposer."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

base_dir = Path(__file__).resolve().parents[2]
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))

from artifacts.candidate_manifest_builder_v1 import build_manifest  # noqa: E402
from artifacts.candidate_tar_writer_v1 import build_candidate_tar_bytes  # noqa: E402
from artifacts.ids_v1 import mechanism_hash  # noqa: E402
from sleep.absop_isa_v1_2 import validate_op_ids  # noqa: E402


def predicted_priority_from_gains(gains: dict[str, Any]) -> int:
    try:
        delta_wcs = float(gains.get("delta_worst_case_success", 0.0))
        delta_eff = float(gains.get("delta_efficiency", 0.0))
        delta_mdl = int(gains.get("delta_mdl_bits", 0))
    except (TypeError, ValueError):
        return 0
    score = int(delta_wcs * 1000) + int(delta_eff * 500) - int(delta_mdl)
    # Lower is better for deterministic sorting.
    return -score


def synthesize_candidates(
    *,
    proposals: list[dict[str, Any]],
    base_ontology: dict[str, Any],
    base_mech: dict[str, Any],
    suite_id_dev: str,
    suite_id_heldout: str,
    claimed_supports_macro_do: bool,
    operator_ranks: dict[str, int],
) -> list[dict[str, Any]]:
    validate_op_ids(proposals)
    candidates: list[dict[str, Any]] = []
    for proposal in proposals:
        ontology_patch = proposal["ontology_patch"]
        if "isa_version" not in ontology_patch:
            isa_version = (
                base_ontology.get("isa_version")
                if isinstance(base_ontology, dict)
                else "caoe_absop_isa_v1_2"
            )
            ontology_patch["isa_version"] = str(isa_version or "caoe_absop_isa_v1_2")
        mech_diff = proposal.get("mech_diff")
        if mech_diff is None:
            mech_diff = {
                "format": "mechanism_registry_diff_v1_1",
                "schema_version": 1,
                "base_mech_hash": mechanism_hash(base_mech),
                "ops": [],
            }
        programs_by_path = proposal.get("program_blobs", {})
        effective_supports_macro_do = bool(claimed_supports_macro_do)
        for op in ontology_patch.get("ops", []):
            if isinstance(op, dict) and op.get("op") == "set_supports_macro_do":
                effective_supports_macro_do = bool(op.get("value"))
        if effective_supports_macro_do:
            obligations = dict(ontology_patch.get("claimed_obligations") or {})
            obligations["requires_c_do"] = True
            ontology_patch["claimed_obligations"] = obligations
        manifest = build_manifest(
            base_ontology=base_ontology,
            base_mech=base_mech,
            suite_id_dev=suite_id_dev,
            suite_id_heldout=suite_id_heldout,
            claimed_supports_macro_do=effective_supports_macro_do,
            ontology_patch=ontology_patch,
            mechanism_diff=mech_diff,
            programs_by_path=programs_by_path,
        )
        tar_bytes = build_candidate_tar_bytes(manifest, ontology_patch, mech_diff, programs_by_path)
        op_id = proposal.get("op_id")
        predicted_priority = predicted_priority_from_gains(proposal.get("predicted_gains", {}))
        candidates.append(
            {
                "candidate_id": manifest["candidate_id"],
                "manifest": manifest,
                "ontology_patch": ontology_patch,
                "mech_diff": mech_diff,
                "programs_by_path": programs_by_path,
                "tar_bytes": tar_bytes,
                "op_id": op_id,
                "predicted_priority": predicted_priority,
                "operator_rank": operator_ranks.get(op_id, 9999),
                "local_meta": {
                    "op_id": op_id,
                    "predicted_gains": proposal.get("predicted_gains", {}),
                    "derivation": proposal.get("derivation", {}),
                    "predicted_priority": predicted_priority,
                    "operator_rank": operator_ranks.get(op_id, 9999),
                },
            }
        )
    candidates.sort(key=lambda c: (c["operator_rank"], c["predicted_priority"], c["candidate_id"]))
    return candidates
