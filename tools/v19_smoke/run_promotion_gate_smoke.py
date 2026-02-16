#!/usr/bin/env python3
"""Promotion-stage smoke harness for v19 continuity gates."""

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
from cdel.v19_0.omega_promoter_v1 import run_promotion
from cdel.v19_0.tests_continuity.helpers import (
    budget,
    canon_hash,
    make_j_profile,
    make_morphism,
    make_overlap_profile,
    make_regime,
    make_totality_cert,
    make_translator_bundle,
    write_object,
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

    with _chdir(subrun_root):
        old_1 = write_object(subrun_root, "continuity/old_1.json", {"x": 1})
        old_2 = write_object(subrun_root, "continuity/old_2.json", {"x": 2})
        old_regime = make_regime(
            subrun_root,
            accepted_artifact_ids=[old_1["artifact_id"], old_2["artifact_id"]],
            prefix="old",
        )
        new_regime = make_regime(
            subrun_root,
            accepted_artifact_ids=[old_1["artifact_id"], old_2["artifact_id"]],
            prefix="new",
        )
        overlap = make_overlap_profile(
            subrun_root,
            refs=[old_1, old_2],
            old_regime=old_regime,
            new_regime=new_regime,
            relpath="continuity/overlap.json",
        )
        translator = make_translator_bundle(
            subrun_root,
            ops=[],
            relpath="continuity/translator.json",
        )
        totality = make_totality_cert(
            subrun_root,
            overlap_ref=overlap,
            translator_ref=translator,
            refs=[old_1, old_2],
            relpath="continuity/totality.json",
        )
        morphism = make_morphism(
            subrun_root,
            overlap_ref=overlap,
            translator_ref=translator,
            totality_ref=totality,
            old_regime=old_regime,
            new_regime=new_regime,
            relpath="continuity/morphism.json",
        )
        sigma_old = write_object(subrun_root, "continuity/sigma_old.json", {"invariant_failures": [{"id": 1}]})
        sigma_new = write_object(subrun_root, "continuity/sigma_new.json", {"invariant_failures": []})
        j_profile = make_j_profile(subrun_root, relpath="continuity/j_profile.json")

        budgets = {
            "continuity_budget": budget(),
            "translator_budget": budget(),
            "receipt_translation_budget": budget(),
            "totality_budget": budget(),
        }
        continuity_receipt = check_continuity(
            sigma_old_ref=sigma_old,
            sigma_new_ref=sigma_new,
            regime_old_ref=old_regime,
            regime_new_ref=new_regime,
            morphism_ref=morphism,
            budgets=budgets,
        )
        continuity_receipt_ref = write_object(
            subrun_root,
            "continuity/continuity_receipt.json",
            continuity_receipt,
            id_field="receipt_id",
        )

        axis_without_id = {
            "schema_name": "axis_upgrade_bundle_v1",
            "schema_version": "v19_0",
            "sigma_old_ref": sigma_old,
            "sigma_new_ref": sigma_new,
            "regime_old_ref": old_regime,
            "regime_new_ref": new_regime,
            "objective_J_profile_ref": j_profile,
            "continuity_budget": budget(),
            "morphisms": [
                {
                    "morphism_ref": morphism,
                    "overlap_profile_ref": overlap,
                    "translator_bundle_ref": translator,
                    "totality_cert_ref": totality,
                    "continuity_receipt_ref": continuity_receipt_ref,
                    "axis_specific_proof_refs": [],
                }
            ],
        }
        axis_bundle = dict(axis_without_id)
        axis_bundle["axis_bundle_id"] = canon_hash(axis_without_id)
        write_canon_json(promotion_dir / "axis_upgrade_bundle_v1.json", axis_bundle)

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
    paths = {
        "continuity_receipt": subrun_root / "continuity" / "continuity_receipt.json",
        "axis_bundle": promotion_dir / "axis_upgrade_bundle_v1.json",
        "totality_cert": subrun_root / "continuity" / "totality.json",
    }
    return dispatch_ctx, paths


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


def main() -> None:
    parser = argparse.ArgumentParser(prog="run_promotion_gate_smoke")
    parser.add_argument(
        "--out_dir",
        default="runs/v19_promotion_gate_smoke",
        help="Output directory for synthetic promotion cases",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    out_dir = (repo_root / args.out_dir).resolve()
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    allowlists, _ = load_allowlists(repo_root / "campaigns" / "rsi_omega_daemon_v19_0" / "omega_allowlists_v1.json")

    case_a = out_dir / "case_a"
    case_b = out_dir / "case_b"
    case_mut = out_dir / "case_mutated_receipt"
    case_no_axis = out_dir / "case_missing_axis"
    case_noncanon = out_dir / "case_noncanonical_axis"
    case_totality = out_dir / "case_totality_fail"

    ctx_a, _ = _prepare_case(case_a)
    ctx_b, _ = _prepare_case(case_b)
    ctx_mut, mut_paths = _prepare_case(case_mut)
    ctx_no_axis, no_axis_paths = _prepare_case(case_no_axis)
    ctx_noncanon, noncanon_paths = _prepare_case(case_noncanon)
    ctx_totality, totality_paths = _prepare_case(case_totality)

    with _patched_v18_promoter():
        receipt_a, digest_a = _run_once(ctx_a, allowlists)
        receipt_b, digest_b = _run_once(ctx_b, allowlists)

        if canon_bytes(receipt_a) != canon_bytes(receipt_b) or digest_a != digest_b:
            raise RuntimeError("NON_DETERMINISTIC_OUTCOME")
        if str(receipt_a.get("result", {}).get("status", "")) != "PROMOTED":
            raise RuntimeError("EXPECTED_PROMOTED")
        _assert_promoted_axis_bundle_integrity(ctx_a)

        tampered = json.loads(mut_paths["continuity_receipt"].read_text(encoding="utf-8"))
        tampered["final_outcome"] = "REJECT"
        write_canon_json(mut_paths["continuity_receipt"], tampered)

        receipt_mut, digest_mut = _run_once(ctx_mut, allowlists)
        if str(receipt_mut.get("result", {}).get("status", "")) == "PROMOTED":
            raise RuntimeError("MUTATION_DID_NOT_FAIL_CLOSED")

        no_axis_paths["axis_bundle"].unlink()
        receipt_no_axis, digest_no_axis = _run_once(ctx_no_axis, allowlists)
        if str(receipt_no_axis.get("result", {}).get("status", "")) == "PROMOTED":
            raise RuntimeError("MISSING_AXIS_DID_NOT_FAIL_CLOSED")

        axis_payload = json.loads(noncanon_paths["axis_bundle"].read_text(encoding="utf-8"))
        noncanon_paths["axis_bundle"].write_text(json.dumps(axis_payload, indent=2) + "\n", encoding="utf-8")
        receipt_noncanon, digest_noncanon = _run_once(ctx_noncanon, allowlists)
        if str(receipt_noncanon.get("result", {}).get("status", "")) == "PROMOTED":
            raise RuntimeError("NONCANON_AXIS_DID_NOT_FAIL_CLOSED")

        totality_payload = json.loads(totality_paths["totality_cert"].read_text(encoding="utf-8"))
        rows = list(totality_payload.get("results", []))
        if rows:
            row0 = dict(rows[0])
            row0["status"] = "FAIL"
            rows[0] = row0
            totality_payload["results"] = rows
        write_canon_json(totality_paths["totality_cert"], totality_payload)
        receipt_totality, digest_totality = _run_once(ctx_totality, allowlists)
        if str(receipt_totality.get("result", {}).get("status", "")) == "PROMOTED":
            raise RuntimeError("TOTALITY_FAIL_DID_NOT_FAIL_CLOSED")

    summary = {
        "deterministic_receipt_digest": digest_a,
        "deterministic_status": receipt_a.get("result", {}).get("status"),
        "mutated_receipt_case": {
            "digest": digest_mut,
            "status": receipt_mut.get("result", {}).get("status"),
            "reason": receipt_mut.get("result", {}).get("reason_code"),
        },
        "missing_axis_case": {
            "digest": digest_no_axis,
            "status": receipt_no_axis.get("result", {}).get("status"),
            "reason": receipt_no_axis.get("result", {}).get("reason_code"),
        },
        "noncanonical_axis_case": {
            "digest": digest_noncanon,
            "status": receipt_noncanon.get("result", {}).get("status"),
            "reason": receipt_noncanon.get("result", {}).get("reason_code"),
        },
        "totality_fail_case": {
            "digest": digest_totality,
            "status": receipt_totality.get("result", {}).get("status"),
            "reason": receipt_totality.get("result", {}).get("reason_code"),
        },
        "case_a_dispatch_dir": str(ctx_a["dispatch_dir"]),
        "case_b_dispatch_dir": str(ctx_b["dispatch_dir"]),
        "case_mutated_dispatch_dir": str(ctx_mut["dispatch_dir"]),
        "case_missing_axis_dispatch_dir": str(ctx_no_axis["dispatch_dir"]),
        "case_noncanonical_axis_dispatch_dir": str(ctx_noncanon["dispatch_dir"]),
        "case_totality_fail_dispatch_dir": str(ctx_totality["dispatch_dir"]),
    }
    summary_path = out_dir / "v19_promotion_gate_smoke_summary.json"
    summary_path.write_text(json.dumps(summary, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    print("PROMOTION_GATE_SMOKE_OK")
    print(f"summary: {summary_path}")


if __name__ == "__main__":
    main()
