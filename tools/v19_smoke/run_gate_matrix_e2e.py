#!/usr/bin/env python3
"""E2E gate-matrix runner for v19 promotion axis enforcement."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "CDEL-v2") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "CDEL-v2"))

import cdel.v18_0.omega_promoter_v1 as v18_promoter
from cdel.v1_7r.canon import canon_bytes, load_canon_json, write_canon_json
from cdel.v18_0.omega_allowlists_v1 import load_allowlists
from cdel.v19_0.continuity.check_continuity_v1 import check_continuity
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
from orchestrator.omega_v19_0.promoter_v1 import run_promotion


MORPHISM_TYPES: tuple[str, ...] = (
    "M_SIGMA",
    "M_PI",
    "M_D",
    "M_H",
    "M_A",
    "M_K",
    "M_E",
    "M_M",
    "M_C",
    "M_W",
    "M_T",
)


@contextmanager
def _chdir(path: Path) -> Iterator[None]:
    prev = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev)


@contextmanager
def _patched_v18_promoter() -> Iterator[None]:
    original_build = v18_promoter._build_meta_core_promotion_bundle
    original_verify = v18_promoter._run_meta_core_promo_verify
    original_activate = v18_promoter._build_meta_core_activation_bundle
    original_read_active = v18_promoter._read_active_binding

    def _fake_build(*, out_dir: Path, campaign_id: str, source_bundle_hash: str) -> Path:
        _ = (campaign_id, source_bundle_hash)
        bundle_dir = out_dir / "meta_core_promotion_bundle_v1"
        bundle_dir.mkdir(parents=True, exist_ok=True)
        return bundle_dir

    def _fake_verify(*, out_dir: Path, bundle_dir: Path) -> tuple[dict[str, Any], bool]:
        _ = (out_dir, bundle_dir)
        return (
            {
                "schema_version": "meta_core_promo_verify_receipt_v1",
                "return_code": 0,
                "stdout_hash": "sha256:" + ("0" * 64),
                "stderr_hash": "sha256:" + ("0" * 64),
                "verifier_out_hash": "sha256:" + ("0" * 64),
                "pass": True,
            },
            True,
        )

    def _fake_activation(
        *,
        out_dir: Path,
        binding_payload: dict[str, Any],
        binding_hash_hex8: str,
    ) -> tuple[Path, str]:
        _ = binding_hash_hex8
        bundle_dir = out_dir / "meta_core_activation_bundle_v1"
        (bundle_dir / "omega").mkdir(parents=True, exist_ok=True)
        write_canon_json(bundle_dir / "omega" / "omega_activation_binding_v1.json", binding_payload)
        return bundle_dir, "sha256:" + ("b" * 64)

    v18_promoter._build_meta_core_promotion_bundle = _fake_build
    v18_promoter._run_meta_core_promo_verify = _fake_verify
    v18_promoter._build_meta_core_activation_bundle = _fake_activation
    v18_promoter._read_active_binding = lambda _root: None
    try:
        yield
    finally:
        v18_promoter._build_meta_core_promotion_bundle = original_build
        v18_promoter._run_meta_core_promo_verify = original_verify
        v18_promoter._build_meta_core_activation_bundle = original_activate
        v18_promoter._read_active_binding = original_read_active


def _prepare_case(case_root: Path) -> tuple[dict[str, Any], dict[str, Path]]:
    state_root = case_root / "daemon" / "rsi_omega_daemon_v19_0" / "state"
    dispatch_dir = state_root / "dispatch" / "a01"
    subrun_root = state_root / "subruns" / "a01_rsi_sas_code_v12_0"
    promotion_dir = subrun_root / "daemon" / "rsi_sas_code_v12_0" / "state" / "promotion"
    promotion_dir.mkdir(parents=True, exist_ok=True)
    dispatch_dir.mkdir(parents=True, exist_ok=True)

    bundle_payload = {
        "schema_version": "sas_code_promotion_bundle_v1",
        "candidate_algo_id": "sha256:" + ("1" * 64),
        "touched_paths": ["CDEL-v2/cdel/v12_0/verify_rsi_sas_code_v1.py"],
    }
    write_canon_json(promotion_dir / "sha256_feedface.sas_code_promotion_bundle_v1.json", bundle_payload)

    dispatch_ctx = {
        "dispatch_dir": dispatch_dir,
        "state_root": state_root,
        "subrun_root_abs": subrun_root,
        "campaign_entry": {
            "campaign_id": "rsi_sas_code_v12_0",
            "capability_id": "RSI_SAS_CODE",
            "promotion_bundle_rel": "daemon/rsi_sas_code_v12_0/state/promotion/*.sas_code_promotion_bundle_v1.json",
        },
    }
    return dispatch_ctx, {
        "state_root": state_root,
        "dispatch_dir": dispatch_dir,
        "subrun_root": subrun_root,
        "promotion_dir": promotion_dir,
    }


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
        "admissible_upgrade_types": [
            "M_K",
            "M_E",
            "M_M",
            "M_C",
            "M_SIGMA",
            "M_PI",
            "M_D",
            "M_H",
            "M_A",
            "M_W",
            "M_T",
        ],
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


def _meta_law_morphism_ref(
    root: Path,
    *,
    constitution_ref: dict[str, str],
    morphism_ref: dict[str, str],
) -> dict[str, str]:
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


def _treaty_proof_refs(
    root: Path,
    *,
    phi_ops: list[dict[str, Any]],
    source_accepts: bool,
    target_accepts: bool,
    include_ok_signature: bool,
) -> list[dict[str, str]]:
    ok_signature = make_ok_signature()
    phi_bundle = make_federation_translator_bundle(phi_ops)
    psi_bundle = make_federation_translator_bundle([])
    overlap_object = {"kind": "claim", "x": 1}
    overlap_object_id = overlap_id(overlap_object)
    ok_signature_id = ok_signature["overlap_signature_id"] if include_ok_signature else ("sha256:" + ("a" * 64))
    treaty = make_treaty(
        ok_signature_id=ok_signature_id,
        phi_bundle_id=phi_bundle["translator_bundle_id"],
        psi_bundle_id=psi_bundle["translator_bundle_id"],
        overlap_test_set_ids=[overlap_object_id],
        dispute_policy="SAFE_SPLIT",
    )
    refs: list[dict[str, str]] = [
        write_object(root, "artifacts/treaty.json", treaty, id_field="treaty_id"),
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
                "source_accepts": bool(source_accepts),
                "target_accepts": bool(target_accepts),
            },
        ),
    ]
    if include_ok_signature:
        refs.append(write_object(root, "artifacts/ok_signature.json", ok_signature, id_field="overlap_signature_id"))
    return refs


def _proof_refs_for_type(
    root: Path,
    *,
    morphism_type: str,
    base: dict[str, Any],
    constitution_ref: dict[str, str] | None,
    treaty_phi_ops: list[dict[str, Any]] | None = None,
    treaty_source_accepts: bool = True,
    treaty_target_accepts: bool = True,
    treaty_include_ok_signature: bool = True,
) -> list[dict[str, str]]:
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
        return _treaty_proof_refs(
            root,
            phi_ops=list(treaty_phi_ops or []),
            source_accepts=treaty_source_accepts,
            target_accepts=treaty_target_accepts,
            include_ok_signature=treaty_include_ok_signature,
        )
    return []


def _axis_bundle(
    *,
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
    return axis


def _write_axis_sidecar(promotion_dir: Path, axis_bundle: dict[str, Any]) -> Path:
    axis_path = promotion_dir / "axis_upgrade_bundle_v1.json"
    write_canon_json(axis_path, axis_bundle)
    return axis_path


def _build_axis_case(
    *,
    subrun_root: Path,
    promotion_dir: Path,
    morphism_type: str,
    variant: str,
) -> None:
    with _chdir(subrun_root):
        base = _base_axis_material(subrun_root, morphism_type=morphism_type)
        constitution_ref = _make_continuity_constitution_ref(subrun_root) if morphism_type in {"M_K", "M_E", "M_M", "M_C"} else None

        if variant == "positive":
            proof_refs = _proof_refs_for_type(
                subrun_root,
                morphism_type=morphism_type,
                base=base,
                constitution_ref=constitution_ref,
            )
            axis_bundle = _axis_bundle(
                base=base,
                proof_refs=proof_refs,
                constitution_ref=constitution_ref,
                negative=False,
            )
        elif variant == "negative_missing_proof":
            proof_refs = _proof_refs_for_type(
                subrun_root,
                morphism_type=morphism_type,
                base=base,
                constitution_ref=constitution_ref,
            )
            axis_bundle = _axis_bundle(
                base=base,
                proof_refs=proof_refs,
                constitution_ref=constitution_ref,
                negative=True,
            )
        elif variant == "negative_treaty_non_total":
            if morphism_type != "M_T":
                raise RuntimeError("treaty non-total variant only valid for M_T")
            proof_refs = _proof_refs_for_type(
                subrun_root,
                morphism_type=morphism_type,
                base=base,
                constitution_ref=constitution_ref,
                treaty_phi_ops=[{"op": "TEST", "path": "/missing", "value": 1}],
                treaty_source_accepts=True,
                treaty_target_accepts=True,
                treaty_include_ok_signature=True,
            )
            axis_bundle = _axis_bundle(
                base=base,
                proof_refs=proof_refs,
                constitution_ref=constitution_ref,
                negative=False,
            )
        elif variant == "negative_treaty_no_new_acceptance":
            if morphism_type != "M_T":
                raise RuntimeError("treaty acceptance variant only valid for M_T")
            proof_refs = _proof_refs_for_type(
                subrun_root,
                morphism_type=morphism_type,
                base=base,
                constitution_ref=constitution_ref,
                treaty_phi_ops=[],
                treaty_source_accepts=False,
                treaty_target_accepts=True,
                treaty_include_ok_signature=True,
            )
            axis_bundle = _axis_bundle(
                base=base,
                proof_refs=proof_refs,
                constitution_ref=constitution_ref,
                negative=False,
            )
        else:
            raise RuntimeError(f"unknown variant: {variant}")

        _write_axis_sidecar(promotion_dir, axis_bundle)


def _run_once(dispatch_ctx: dict[str, Any], allowlists: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    subverifier_receipt = {"result": {"status": "VALID", "reason_code": None}}
    try:
        with _chdir(Path(dispatch_ctx["subrun_root_abs"])):
            receipt, digest = run_promotion(
                tick_u64=1,
                dispatch_ctx=dispatch_ctx,
                subverifier_receipt=subverifier_receipt,
                allowlists=allowlists,
            )
    except Exception as exc:  # noqa: BLE001
        return {
            "result": {
                "status": "EXCEPTION",
                "reason_code": f"{exc.__class__.__name__}:{exc}",
            }
        }, None
    if receipt is None:
        raise RuntimeError("promotion returned no receipt")
    return receipt, digest


def _status(receipt: dict[str, Any]) -> str:
    return str((receipt.get("result") or {}).get("status", ""))


def _reason(receipt: dict[str, Any]) -> str:
    return str((receipt.get("result") or {}).get("reason_code", ""))


def _assert_promoted_axis_bundle_integrity(dispatch_ctx: dict[str, Any]) -> None:
    axis_path = (
        Path(dispatch_ctx["dispatch_dir"])
        / "promotion"
        / "meta_core_promotion_bundle_v1"
        / "omega"
        / "axis_upgrade_bundle_v1.json"
    )
    if not axis_path.is_file():
        raise RuntimeError("PROMOTED_AXIS_BUNDLE_MISSING")

    try:
        payload = load_canon_json(axis_path)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("PROMOTED_AXIS_BUNDLE_NONCANONICAL") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("PROMOTED_AXIS_BUNDLE_SCHEMA_FAIL")

    declared = str(payload.get("axis_bundle_id", "")).strip()
    if not declared:
        raise RuntimeError("PROMOTED_AXIS_BUNDLE_ID_MISSING")

    without_id = dict(payload)
    without_id.pop("axis_bundle_id", None)
    expected = canon_hash(without_id)
    if declared != expected:
        raise RuntimeError("PROMOTED_AXIS_BUNDLE_ID_MISMATCH")


def _assert_axis_gate_failure(
    promotion_dir: Path,
    *,
    expected_outcomes: set[str],
    detail_prefix: str | None = None,
) -> tuple[str, str]:
    gate_failure_path = promotion_dir / "axis_gate_failure_v1.json"
    if not gate_failure_path.is_file():
        raise RuntimeError("AXIS_GATE_FAILURE_MISSING")
    payload = load_canon_json(gate_failure_path)
    if not isinstance(payload, dict):
        raise RuntimeError("AXIS_GATE_FAILURE_SCHEMA_FAIL")

    outcome = str(payload.get("outcome", "")).strip()
    detail = str(payload.get("detail", "")).strip()
    if outcome not in expected_outcomes:
        raise RuntimeError(f"AXIS_GATE_FAILURE_OUTCOME_MISMATCH:{outcome}")
    if detail_prefix is not None and not detail.startswith(detail_prefix):
        raise RuntimeError(f"AXIS_GATE_FAILURE_DETAIL_MISMATCH:{detail}")
    return outcome, detail


def _run_positive_pair(
    *,
    out_dir: Path,
    morphism_type: str,
    allowlists: dict[str, Any],
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "morphism_type": morphism_type,
        "variant": "positive_ab_determinism",
    }
    try:
        case_a = out_dir / f"{morphism_type}_positive_a"
        case_b = out_dir / f"{morphism_type}_positive_b"
        ctx_a, paths_a = _prepare_case(case_a)
        ctx_b, paths_b = _prepare_case(case_b)
        _build_axis_case(
            subrun_root=paths_a["subrun_root"],
            promotion_dir=paths_a["promotion_dir"],
            morphism_type=morphism_type,
            variant="positive",
        )
        _build_axis_case(
            subrun_root=paths_b["subrun_root"],
            promotion_dir=paths_b["promotion_dir"],
            morphism_type=morphism_type,
            variant="positive",
        )

        receipt_a, digest_a = _run_once(ctx_a, allowlists)
        receipt_b, digest_b = _run_once(ctx_b, allowlists)

        status_a = _status(receipt_a)
        status_b = _status(receipt_b)
        reason_a = _reason(receipt_a)
        reason_b = _reason(receipt_b)

        deterministic_receipt = canon_bytes(receipt_a) == canon_bytes(receipt_b)
        deterministic_digest = digest_a == digest_b

        _assert_promoted_axis_bundle_integrity(ctx_a)
        _assert_promoted_axis_bundle_integrity(ctx_b)

        row.update(
            {
                "dispatch_dir_a": str(ctx_a["dispatch_dir"]),
                "dispatch_dir_b": str(ctx_b["dispatch_dir"]),
                "status_a": status_a,
                "status_b": status_b,
                "reason_a": reason_a,
                "reason_b": reason_b,
                "digest_a": digest_a,
                "digest_b": digest_b,
                "deterministic_receipt": deterministic_receipt,
                "deterministic_digest": deterministic_digest,
                "passes": status_a == "PROMOTED"
                and status_b == "PROMOTED"
                and deterministic_receipt
                and deterministic_digest,
            }
        )
    except Exception as exc:  # noqa: BLE001
        row["passes"] = False
        row["error"] = f"{exc.__class__.__name__}:{exc}"
    return row


def _run_negative_case(
    *,
    out_dir: Path,
    morphism_type: str,
    variant: str,
    allowlists: dict[str, Any],
    expected_outcomes: set[str],
    detail_prefix: str | None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "morphism_type": morphism_type,
        "variant": variant,
    }
    try:
        case_root = out_dir / f"{morphism_type}_{variant}"
        ctx, paths = _prepare_case(case_root)
        _build_axis_case(
            subrun_root=paths["subrun_root"],
            promotion_dir=paths["promotion_dir"],
            morphism_type=morphism_type,
            variant=variant,
        )
        receipt, digest = _run_once(ctx, allowlists)

        status = _status(receipt)
        reason = _reason(receipt)
        gate_outcome, gate_detail = _assert_axis_gate_failure(
            paths["promotion_dir"],
            expected_outcomes=expected_outcomes,
            detail_prefix=detail_prefix,
        )

        row.update(
            {
                "dispatch_dir": str(ctx["dispatch_dir"]),
                "status": status,
                "reason": reason,
                "digest": digest,
                "gate_outcome": gate_outcome,
                "gate_detail": gate_detail,
                "passes": status != "PROMOTED" and gate_outcome in {"SAFE_HALT", "SAFE_SPLIT"},
            }
        )
    except Exception as exc:  # noqa: BLE001
        row["passes"] = False
        row["error"] = f"{exc.__class__.__name__}:{exc}"
    return row


def run_gate_matrix(*, out_dir: Path) -> dict[str, Any]:
    out_dir = out_dir.resolve()
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    allowlists, _ = load_allowlists(REPO_ROOT / "campaigns" / "rsi_omega_daemon_v19_0" / "omega_allowlists_v1.json")

    rows: list[dict[str, Any]] = []
    with _patched_v18_promoter():
        for morphism_type in MORPHISM_TYPES:
            rows.append(_run_positive_pair(out_dir=out_dir, morphism_type=morphism_type, allowlists=allowlists))
            rows.append(
                _run_negative_case(
                    out_dir=out_dir,
                    morphism_type=morphism_type,
                    variant="negative_missing_proof",
                    allowlists=allowlists,
                    expected_outcomes={"SAFE_HALT", "SAFE_SPLIT"},
                    detail_prefix=None,
                )
            )

            if morphism_type == "M_T":
                rows.append(
                    _run_negative_case(
                        out_dir=out_dir,
                        morphism_type="M_T",
                        variant="negative_treaty_non_total",
                        allowlists=allowlists,
                        expected_outcomes={"SAFE_SPLIT"},
                        detail_prefix="SAFE_SPLIT:TRANSLATOR_NON_TOTAL",
                    )
                )
                rows.append(
                    _run_negative_case(
                        out_dir=out_dir,
                        morphism_type="M_T",
                        variant="negative_treaty_no_new_acceptance",
                        allowlists=allowlists,
                        expected_outcomes={"SAFE_SPLIT"},
                        detail_prefix="SAFE_SPLIT:NO_NEW_ACCEPTANCE_PATH",
                    )
                )

    summary = {
        "schema_name": "v19_gate_matrix_summary_v1",
        "schema_version": "v19_0",
        "rows": rows,
        "all_passed": all(bool(row.get("passes", False)) for row in rows),
    }
    write_canon_json(out_dir / "v19_gate_matrix_summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run v19 promotion gate matrix e2e harness")
    parser.add_argument(
        "--out_dir",
        default="runs/v19_gate_matrix_e2e",
        help="Output directory for gate-matrix artifacts",
    )
    args = parser.parse_args()

    summary = run_gate_matrix(out_dir=Path(args.out_dir))
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if bool(summary.get("all_passed", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
