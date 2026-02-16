#!/usr/bin/env python3
"""L0-L11 ladder harness for v19 promotion-gate enforcement."""

from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "CDEL-v2") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "CDEL-v2"))

from cdel.v1_7r.canon import load_canon_json, write_canon_json
from cdel.v19_0.continuity.check_continuity_v1 import check_continuity
from cdel.v19_0.continuity.common_v1 import ContinuityV19Error
from cdel.v19_0.omega_promoter_v1 import _verify_axis_bundle_gate
from cdel.v19_0.tests_continuity.helpers import (
    budget as continuity_budget,
    canon_hash,
    make_j_profile,
    make_morphism,
    make_overlap_profile,
    make_regime,
    make_totality_cert,
    make_translator_bundle as make_continuity_translator_bundle,
    write_object,
)
from cdel.v19_0.tests_world_federation.helpers import (
    budget as federation_budget,
    make_entry,
    make_manifest,
    make_ok_signature,
    make_sip_profile,
    make_treaty,
    make_translator_bundle as make_federation_translator_bundle,
    make_world_snapshot,
    overlap_id,
)
from cdel.v19_0.world.merkle_v1 import compute_world_root
from cdel.v19_0.world.sip_v1 import run_sip


LEVELS: tuple[tuple[str, str], ...] = (
    ("L0", "M_SIGMA"),
    ("L1", "M_SIGMA"),
    ("L2", "M_PI"),
    ("L3", "M_D"),
    ("L4", "M_H"),
    ("L5", "M_A"),
    ("L6", "M_K"),
    ("L7", "M_E"),
    ("L8", "M_M"),
    ("L9", "M_C"),
    ("L10", "M_W"),
    ("L11", "M_T"),
)


@contextmanager
def _chdir(path: Path):
    prev = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev)


def _base_axis_material(root: Path, *, morphism_type: str) -> dict[str, Any]:
    old_1 = write_object(root, "artifacts/old_1.json", {"x": 1})
    old_2 = write_object(root, "artifacts/old_2.json", {"x": 2})
    regime_old = make_regime(
        root,
        accepted_artifact_ids=[old_1["artifact_id"], old_2["artifact_id"]],
        prefix="old",
    )
    regime_new = make_regime(
        root,
        accepted_artifact_ids=[old_1["artifact_id"], old_2["artifact_id"]],
        prefix="new",
    )
    overlap = make_overlap_profile(root, refs=[old_1, old_2], old_regime=regime_old, new_regime=regime_new)
    translator = make_continuity_translator_bundle(root, ops=[])
    totality = make_totality_cert(root, overlap_ref=overlap, translator_ref=translator, refs=[old_1, old_2])
    morphism_ref = make_morphism(
        root,
        overlap_ref=overlap,
        translator_ref=translator,
        totality_ref=totality,
        old_regime=regime_old,
        new_regime=regime_new,
    )
    morphism_payload = load_canon_json(root / str(morphism_ref["artifact_relpath"]))
    morphism_payload = dict(morphism_payload)
    morphism_payload["morphism_type"] = morphism_type
    if morphism_type == "M_D":
        morphism_payload["epsilon_udc_u64"] = 0
        schedule = write_object(
            root,
            "artifacts/udc_schedule.json",
            {
                "schema_name": "udc_schedule_v1",
                "schema_version": "v19_0",
                "schedule_id": "sha256:" + ("0" * 64),
                "entries": [{"task_id": "t0", "cost_u64": 1}],
            },
            id_field="schedule_id",
        )
        morphism_payload["udc_schedule_ref"] = schedule
    if morphism_type == "M_H":
        constructor_cert = write_object(
            root,
            "artifacts/constructor_conservativity_cert.json",
            {
                "schema_name": "constructor_conservativity_cert_v1",
                "schema_version": "v19_0",
                "cert_id": "sha256:" + ("0" * 64),
                "overlap_profile_id": str(overlap["artifact_id"]),
                "result": "PASS",
                "reason_code": "PASS",
            },
            id_field="cert_id",
        )
        morphism_payload["constructor_conservativity_cert_ref"] = constructor_cert
    if morphism_type == "M_A":
        meta_budget = continuity_budget()
        meta_budget_no_id = dict(meta_budget)
        meta_budget_no_id.pop("budget_spec_id", None)
        meta_budget_id = canon_hash(meta_budget_no_id)
        morphism_payload["meta_yield_cert_ref"] = write_object(
            root,
            "artifacts/meta_yield_cert.json",
            {
                "schema_name": "meta_yield_cert_v1",
                "schema_version": "v19_0",
                "cert_id": "sha256:" + ("0" * 64),
                "horizon_u64": 1,
                "suite_id": "suite",
                "budget_spec_id": meta_budget_id,
                "y_series": [0],
            },
            id_field="cert_id",
        )
    if morphism_type == "M_PI":
        morphism_payload["representation_mode"] = "INJECTIVE"
        morphism_payload["decoder_artifact_refs"] = [write_object(root, "artifacts/decoder.json", {"decoder": 1})]
        morphism_payload["collision_suite_ref"] = write_object(root, "artifacts/collision_suite.json", {"suite": 1})

    morphism_ref = write_object(
        root,
        f"artifacts/morphism_{morphism_type}.json",
        morphism_payload,
        id_field="morphism_id",
    )
    sigma_old = write_object(root, "artifacts/sigma_old.json", {"invariant_failures": [{"id": 1}]})
    sigma_new = write_object(root, "artifacts/sigma_new.json", {"invariant_failures": []})
    j_profile = make_j_profile(root, relpath="artifacts/j_profile.json")
    budgets = {
        "continuity_budget": continuity_budget(),
        "translator_budget": continuity_budget(),
        "receipt_translation_budget": continuity_budget(),
        "totality_budget": continuity_budget(),
    }
    with _chdir(root):
        continuity_receipt = check_continuity(
            sigma_old_ref=sigma_old,
            sigma_new_ref=sigma_new,
            regime_old_ref=regime_old,
            regime_new_ref=regime_new,
            morphism_ref=morphism_ref,
            budgets=budgets,
        )
    continuity_receipt_ref = write_object(
        root,
        f"artifacts/continuity_receipt_{morphism_type}.json",
        continuity_receipt,
        id_field="receipt_id",
    )
    return {
        "sigma_old": sigma_old,
        "sigma_new": sigma_new,
        "regime_old": regime_old,
        "regime_new": regime_new,
        "j_profile": j_profile,
        "morphism": morphism_ref,
        "overlap": overlap,
        "translator": translator,
        "totality": totality,
        "continuity_receipt": continuity_receipt_ref,
    }


def _make_continuity_constitution_ref(root: Path) -> dict[str, str]:
    payload = {
        "schema_name": "continuity_constitution_v1",
        "schema_version": "v19_0",
        "constitution_id": "sha256:" + ("0" * 64),
        "admissible_upgrade_types": ["M_K", "M_E", "M_M", "M_C", "M_SIGMA", "M_PI", "M_D", "M_H", "M_A", "M_W", "M_T"],
        "required_proof_map": {"M_K": [], "M_E": [], "M_M": [], "M_C": []},
        "epsilon_terms": {"epsilon_J": 1, "epsilon_udc": 0},
        "debt_amortization_horizons": {"TDL": 1},
        "required_reason_codes": ["SCHEMA_ERROR"],
        "safe_policy_defaults": {
            "on_missing_artifact": "SAFE_HALT",
            "on_budget_exhausted": "SAFE_HALT",
            "on_unresolved_overlap": "SAFE_HALT",
        },
        "kernel_polarity_rules": {"single_k_plus_required": False, "default_other_polarity": "K_MINUS"},
    }
    return write_object(root, "artifacts/continuity_constitution.json", payload, id_field="constitution_id")


def _kernel_upgrade_ref(root: Path) -> dict[str, str]:
    old_kernel = write_object(root, "artifacts/old_kernel.json", {"kernel": "old"})
    new_kernel = write_object(root, "artifacts/new_kernel.json", {"kernel": "new"})
    bootstrap = write_object(root, "artifacts/kernel_bootstrap_receipt.json", {"receipt": "ok"})
    translator = write_object(root, "artifacts/kernel_receipt_translator.json", {"translator": "ok"})
    tests = write_object(root, "artifacts/kernel_determinism_tests.json", {"tests": ["determinism"]})
    payload = {
        "schema_name": "kernel_upgrade_v1",
        "schema_version": "v19_0",
        "upgrade_id": "sha256:" + ("0" * 64),
        "old_kernel_ref": old_kernel,
        "new_kernel_ref": new_kernel,
        "bootstrap_receipt_ref": bootstrap,
        "receipt_translator_bundle_ref": translator,
        "determinism_conformance_tests_ref": tests,
        "polarity": "K_PLUS",
        "equivalence_or_extension_proof_ref": None,
    }
    return write_object(root, "artifacts/kernel_upgrade.json", payload, id_field="upgrade_id")


def _env_upgrade_ref(root: Path) -> dict[str, str]:
    old_env = write_object(root, "artifacts/old_env.json", {"env": "old"})
    new_env = write_object(root, "artifacts/new_env.json", {"env": "new"})
    envelope = write_object(
        root,
        "artifacts/hardness_envelope.json",
        {"task_answer_pairs": [{"task_text": "task", "answer_text": "answer"}]},
    )
    payload = {
        "schema_name": "env_upgrade_v1",
        "schema_version": "v19_0",
        "upgrade_id": "sha256:" + ("0" * 64),
        "old_env_ref": old_env,
        "new_env_ref": new_env,
        "reduction_witness": {
            "lift": [{"old_task_id": "old_task", "new_task_id": "new_task"}],
            "proj": [{"new_answer_id": "new_answer", "old_answer_id": "old_answer"}],
            "implication_checks": [
                {
                    "lift_task_id": "new_task",
                    "projected_answer_id": "old_answer",
                    "implication_holds": True,
                }
            ],
        },
        "hardness_envelope_ref": envelope,
        "anti_leak_scanner_ref": None,
    }
    return write_object(root, "artifacts/env_upgrade.json", payload, id_field="upgrade_id")


def _constitution_morphism_ref(root: Path) -> dict[str, str]:
    old_const = _make_continuity_constitution_ref(root)
    new_const = _make_continuity_constitution_ref(root)
    ck_profile = write_object(
        root,
        "artifacts/ck_profile.json",
        {
            "schema_name": "constitution_kernel_profile_v1",
            "schema_version": "v19_0",
            "ck_profile_id": "sha256:" + ("0" * 64),
            "ck_checker_module_hash": "sha256:" + ("1" * 64),
            "checked_fields": ["required_proof_map", "admissible_upgrade_types"],
            "pinned_fragment_ids": ["sha256:" + ("2" * 64)],
        },
        id_field="ck_profile_id",
    )
    payload = {
        "schema_name": "constitution_morphism_v1",
        "schema_version": "v19_0",
        "morphism_id": "sha256:" + ("0" * 64),
        "old_constitution_ref": old_const,
        "new_constitution_ref": new_const,
        "ck_profile_ref": ck_profile,
        "change_class": "CONSERVATIVE_EXTENSION",
        "required_proofs": ["CONSTITUTION_KERNEL_COMPLIANCE"],
        "translator_totality_required": False,
        "constitutional_backrefute_required": False,
    }
    return write_object(root, "artifacts/constitution_morphism.json", payload, id_field="morphism_id")


def _meta_law_morphism_ref(root: Path, *, constitution_ref: dict[str, str], morphism_ref: dict[str, str]) -> dict[str, str]:
    payload = {
        "schema_name": "meta_law_morphism_v1",
        "schema_version": "v19_0",
        "morphism_id": "sha256:" + ("0" * 64),
        "continuity_constitution_ref": constitution_ref,
        "target_morphism_ref": morphism_ref,
        "required_proofs": ["META_LAW_COMPLIANCE"],
    }
    return write_object(root, "artifacts/meta_law_morphism.json", payload, id_field="morphism_id")


def _world_proof_refs(root: Path) -> list[dict[str, str]]:
    entry = make_entry("inputs/a.txt", b"alpha")
    manifest = make_manifest([entry])
    world_root = compute_world_root(manifest)
    snapshot_id = "sha256:" + ("8" * 64)
    ingestion_receipt = run_sip(
        manifest=manifest,
        artifact_bytes_by_content_id={entry["content_id"]: b"alpha"},
        sip_profile=make_sip_profile(),
        world_task_bindings=[],
        world_snapshot_id=snapshot_id,
        budget_spec=federation_budget(),
    )
    snapshot = make_world_snapshot(
        manifest=manifest,
        ingestion_receipt=ingestion_receipt,
        world_root=world_root,
    )
    return [
        write_object(root, "artifacts/world_snapshot.json", snapshot, id_field="world_snapshot_id"),
        write_object(root, "artifacts/world_manifest.json", manifest, id_field="manifest_id"),
        write_object(root, "artifacts/ingestion_receipt.json", ingestion_receipt, id_field="receipt_id"),
    ]


def _treaty_proof_refs(root: Path) -> list[dict[str, str]]:
    ok_signature = make_ok_signature()
    phi_bundle = make_federation_translator_bundle([])
    psi_bundle = make_federation_translator_bundle([])
    overlap_object = {"kind": "claim", "x": 1}
    overlap_object_id = overlap_id(overlap_object)
    treaty = make_treaty(
        ok_signature_id=ok_signature["overlap_signature_id"],
        phi_bundle_id=phi_bundle["translator_bundle_id"],
        psi_bundle_id=psi_bundle["translator_bundle_id"],
        overlap_test_set_ids=[overlap_object_id],
        dispute_policy="SAFE_SPLIT",
    )
    return [
        write_object(root, "artifacts/treaty.json", treaty, id_field="treaty_id"),
        write_object(root, "artifacts/ok_signature.json", ok_signature, id_field="overlap_signature_id"),
        write_object(root, "artifacts/phi_bundle.json", phi_bundle, id_field="translator_bundle_id"),
        write_object(root, "artifacts/psi_bundle.json", psi_bundle, id_field="translator_bundle_id"),
        write_object(
            root,
            "artifacts/overlap_object.json",
            {
                "schema_name": "overlap_test_object_v1",
                "schema_version": "v19_0",
                "overlap_object_id": overlap_object_id,
                "object": overlap_object,
            },
        ),
        write_object(
            root,
            "artifacts/treaty_acceptance_profile.json",
            {
                "schema_name": "treaty_acceptance_profile_v1",
                "schema_version": "v19_0",
                "source_accepts": True,
                "target_accepts": True,
            },
        ),
    ]


def _axis_bundle(
    *,
    root: Path,
    base: dict[str, Any],
    proof_refs: list[dict[str, str]],
    constitution_ref: dict[str, str] | None = None,
    negative: bool = False,
) -> dict[str, Any]:
    morphism_entry: dict[str, Any] = {
        "morphism_ref": base["morphism"],
        "overlap_profile_ref": base["overlap"],
        "translator_bundle_ref": base["translator"],
        "totality_cert_ref": base["totality"],
        "continuity_receipt_ref": base["continuity_receipt"],
        "axis_specific_proof_refs": list(proof_refs),
    }
    if negative:
        if proof_refs:
            morphism_entry["axis_specific_proof_refs"] = list(proof_refs[1:])
        else:
            morphism_entry["continuity_receipt_ref"] = {
                "artifact_id": "sha256:" + ("f" * 64),
                "artifact_relpath": "artifacts/missing_continuity_receipt.json",
            }
    axis_without_id: dict[str, Any] = {
        "schema_name": "axis_upgrade_bundle_v1",
        "schema_version": "v19_0",
        "sigma_old_ref": base["sigma_old"],
        "sigma_new_ref": base["sigma_new"],
        "regime_old_ref": base["regime_old"],
        "regime_new_ref": base["regime_new"],
        "objective_J_profile_ref": base["j_profile"],
        "continuity_budget": continuity_budget(),
        "morphisms": [morphism_entry],
    }
    if constitution_ref is not None:
        axis_without_id["continuity_constitution_ref"] = constitution_ref
    axis = dict(axis_without_id)
    axis["axis_bundle_id"] = canon_hash(axis_without_id)
    write_canon_json(root / "promotion_bundle" / "axis_upgrade_bundle_v1.json", axis)
    return axis


def _gate_outcome(*, root: Path, axis_bundle: dict[str, Any]) -> tuple[str, str]:
    promotion_bundle = root / "promotion_bundle"
    promotion_bundle.mkdir(parents=True, exist_ok=True)
    bundle_obj = {"touched_paths": ["CDEL-v2/cdel/v19_0/omega_promoter_v1.py"]}
    bundle_path = promotion_bundle / "bundle.json"
    write_canon_json(bundle_path, bundle_obj)
    write_canon_json(promotion_bundle / "axis_upgrade_bundle_v1.json", axis_bundle)
    promotion_dir = root / "promotion_receipts"
    promotion_dir.mkdir(parents=True, exist_ok=True)
    with _chdir(root):
        try:
            _verify_axis_bundle_gate(
                bundle_obj=bundle_obj,
                bundle_path=bundle_path,
                promotion_dir=promotion_dir,
            )
            return "ACCEPT", "PASS"
        except ContinuityV19Error as exc:
            detail = str(exc)
            if detail.startswith("SAFE_SPLIT:"):
                return "SAFE_SPLIT", detail
            return "SAFE_HALT", detail


def _proof_refs_for_type(root: Path, *, morphism_type: str, base: dict[str, Any], constitution_ref: dict[str, str] | None) -> list[dict[str, str]]:
    if morphism_type == "M_K":
        return [_kernel_upgrade_ref(root)]
    if morphism_type == "M_E":
        return [_env_upgrade_ref(root)]
    if morphism_type == "M_C":
        return [_constitution_morphism_ref(root)]
    if morphism_type == "M_M":
        if constitution_ref is None:
            raise RuntimeError("constitution ref missing for M_M")
        return [_meta_law_morphism_ref(root, constitution_ref=constitution_ref, morphism_ref=base["morphism"])]
    if morphism_type == "M_W":
        return _world_proof_refs(root)
    if morphism_type == "M_T":
        return _treaty_proof_refs(root)
    return []


def run_ladder(*, out_dir: Path) -> dict[str, Any]:
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for level, morphism_type in LEVELS:
        case_root = out_dir / f"{level}_{morphism_type}"
        case_root.mkdir(parents=True, exist_ok=True)
        base = _base_axis_material(case_root, morphism_type=morphism_type)
        constitution_ref = _make_continuity_constitution_ref(case_root) if morphism_type in {"M_K", "M_E", "M_M", "M_C"} else None
        proof_refs = _proof_refs_for_type(case_root, morphism_type=morphism_type, base=base, constitution_ref=constitution_ref)

        axis_positive = _axis_bundle(
            root=case_root,
            base=base,
            proof_refs=proof_refs,
            constitution_ref=constitution_ref,
            negative=False,
        )
        pos_outcome, pos_detail = _gate_outcome(root=case_root, axis_bundle=axis_positive)

        axis_negative = _axis_bundle(
            root=case_root,
            base=base,
            proof_refs=proof_refs,
            constitution_ref=constitution_ref,
            negative=True,
        )
        neg_outcome, neg_detail = _gate_outcome(root=case_root, axis_bundle=axis_negative)
        row = {
            "level": level,
            "morphism_type": morphism_type,
            "positive_outcome": pos_outcome,
            "positive_detail": pos_detail,
            "negative_outcome": neg_outcome,
            "negative_detail": neg_detail,
            "passes": pos_outcome == "ACCEPT" and neg_outcome in {"SAFE_HALT", "SAFE_SPLIT"},
        }
        rows.append(row)

    summary = {
        "schema_name": "v19_ladder_summary_v1",
        "schema_version": "v19_0",
        "rows": rows,
        "all_passed": all(bool(row.get("passes", False)) for row in rows),
    }
    write_canon_json(out_dir / "v19_ladder_summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run v19 L0-L11 ladder harness")
    parser.add_argument("--out_dir", default="runs/v19_ladder", help="Output directory for harness artifacts")
    args = parser.parse_args()

    summary = run_ladder(out_dir=Path(args.out_dir))
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if bool(summary.get("all_passed", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
