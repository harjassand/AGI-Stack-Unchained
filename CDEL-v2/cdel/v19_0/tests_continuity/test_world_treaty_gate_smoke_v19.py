from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

import pytest

_CDEL_ROOT = Path(__file__).resolve().parents[3]
if str(_CDEL_ROOT) not in sys.path:
    sys.path.insert(0, str(_CDEL_ROOT))

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


def _base_axis_material(tmp_path: Path, *, morphism_type: str) -> dict[str, Any]:
    old_1 = write_object(tmp_path, "artifacts/old_1.json", {"x": 1})
    old_2 = write_object(tmp_path, "artifacts/old_2.json", {"x": 2})
    regime_old = make_regime(
        tmp_path,
        accepted_artifact_ids=[old_1["artifact_id"], old_2["artifact_id"]],
        prefix="old",
    )
    regime_new = make_regime(
        tmp_path,
        accepted_artifact_ids=[old_1["artifact_id"], old_2["artifact_id"]],
        prefix="new",
    )
    overlap = make_overlap_profile(
        tmp_path,
        refs=[old_1, old_2],
        old_regime=regime_old,
        new_regime=regime_new,
    )
    translator = make_continuity_translator_bundle(tmp_path, ops=[])
    totality = make_totality_cert(
        tmp_path,
        overlap_ref=overlap,
        translator_ref=translator,
        refs=[old_1, old_2],
    )
    morphism_ref = make_morphism(
        tmp_path,
        overlap_ref=overlap,
        translator_ref=translator,
        totality_ref=totality,
        old_regime=regime_old,
        new_regime=regime_new,
    )
    morphism_payload = load_canon_json(tmp_path / str(morphism_ref["artifact_relpath"]))
    morphism_payload = dict(morphism_payload)
    morphism_payload["morphism_type"] = morphism_type
    morphism_ref = write_object(
        tmp_path,
        f"artifacts/morphism_{morphism_type}.json",
        morphism_payload,
        id_field="morphism_id",
    )

    sigma_old = write_object(tmp_path, "artifacts/sigma_old.json", {"invariant_failures": [{"id": 1}]})
    sigma_new = write_object(tmp_path, "artifacts/sigma_new.json", {"invariant_failures": []})
    j_profile = make_j_profile(tmp_path, relpath="artifacts/j_profile.json")
    budgets = {
        "continuity_budget": continuity_budget(),
        "translator_budget": continuity_budget(),
        "receipt_translation_budget": continuity_budget(),
        "totality_budget": continuity_budget(),
    }
    continuity_receipt = check_continuity(
        sigma_old_ref=sigma_old,
        sigma_new_ref=sigma_new,
        regime_old_ref=regime_old,
        regime_new_ref=regime_new,
        morphism_ref=morphism_ref,
        budgets=budgets,
    )
    continuity_receipt_ref = write_object(
        tmp_path,
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


def _invoke_gate(tmp_path: Path, *, axis_bundle: dict[str, Any]) -> None:
    promotion_root = tmp_path / "promotion_bundle"
    promotion_root.mkdir(parents=True, exist_ok=True)
    bundle_obj = {"touched_paths": ["CDEL-v2/cdel/v19_0/omega_promoter_v1.py"]}
    bundle_path = promotion_root / "bundle.json"
    write_canon_json(bundle_path, bundle_obj)
    write_canon_json(promotion_root / "axis_upgrade_bundle_v1.json", axis_bundle)
    promotion_dir = tmp_path / "promotion_receipts"
    promotion_dir.mkdir(parents=True, exist_ok=True)
    _verify_axis_bundle_gate(
        bundle_obj=bundle_obj,
        bundle_path=bundle_path,
        promotion_dir=promotion_dir,
    )


def _axis_bundle(base: dict[str, Any], axis_specific_proofs: list[dict[str, str]]) -> dict[str, Any]:
    axis_without_id = {
        "schema_name": "axis_upgrade_bundle_v1",
        "schema_version": "v19_0",
        "sigma_old_ref": base["sigma_old"],
        "sigma_new_ref": base["sigma_new"],
        "regime_old_ref": base["regime_old"],
        "regime_new_ref": base["regime_new"],
        "objective_J_profile_ref": base["j_profile"],
        "continuity_budget": continuity_budget(),
        "morphisms": [
            {
                "morphism_ref": base["morphism"],
                "overlap_profile_ref": base["overlap"],
                "translator_bundle_ref": base["translator"],
                "totality_cert_ref": base["totality"],
                "continuity_receipt_ref": base["continuity_receipt"],
                "axis_specific_proof_refs": axis_specific_proofs,
            }
        ],
    }
    axis = dict(axis_without_id)
    axis["axis_bundle_id"] = canon_hash(axis_without_id)
    return axis


def test_gate_accepts_world_morphism_when_snapshot_artifacts_valid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    base = _base_axis_material(tmp_path, morphism_type="M_W")

    entry = make_entry("inputs/a.txt", b"alpha")
    manifest = make_manifest([entry])
    world_root = compute_world_root(manifest)
    snapshot_id = "sha256:" + ("9" * 64)
    ingestion_receipt = run_sip(
        manifest=manifest,
        artifact_bytes_by_content_id={entry["content_id"]: b"alpha"},
        sip_profile=make_sip_profile(),
        world_task_bindings=[],
        world_snapshot_id=snapshot_id,
        budget_spec=federation_budget(),
    )
    assert ingestion_receipt["outcome"] == "ACCEPT"
    snapshot = make_world_snapshot(
        manifest=manifest,
        ingestion_receipt=ingestion_receipt,
        world_root=world_root,
    )

    snapshot_ref = write_object(tmp_path, "artifacts/world_snapshot.json", snapshot, id_field="world_snapshot_id")
    manifest_ref = write_object(tmp_path, "artifacts/world_manifest.json", manifest, id_field="manifest_id")
    ingestion_ref = write_object(tmp_path, "artifacts/ingestion_receipt.json", ingestion_receipt, id_field="receipt_id")
    axis = _axis_bundle(base, [snapshot_ref, manifest_ref, ingestion_ref])

    _invoke_gate(tmp_path, axis_bundle=axis)


def test_gate_halts_world_morphism_when_world_root_mismatches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    base = _base_axis_material(tmp_path, morphism_type="M_W")

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
    assert ingestion_receipt["outcome"] == "ACCEPT"
    bad_snapshot = make_world_snapshot(
        manifest=manifest,
        ingestion_receipt=ingestion_receipt,
        world_root="sha256:" + ("f" * 64),
    )
    assert bad_snapshot["world_root"] != world_root

    snapshot_ref = write_object(tmp_path, "artifacts/world_snapshot_bad.json", bad_snapshot, id_field="world_snapshot_id")
    manifest_ref = write_object(tmp_path, "artifacts/world_manifest_bad.json", manifest, id_field="manifest_id")
    ingestion_ref = write_object(
        tmp_path,
        "artifacts/ingestion_receipt_bad.json",
        ingestion_receipt,
        id_field="receipt_id",
    )
    axis = _axis_bundle(base, [snapshot_ref, manifest_ref, ingestion_ref])

    with pytest.raises(ContinuityV19Error, match="SAFE_HALT"):
        _invoke_gate(tmp_path, axis_bundle=axis)


def _treaty_axis(
    tmp_path: Path,
    *,
    phi_ops: list[dict[str, Any]],
    include_ok_signature: bool,
    source_accepts: bool = True,
    target_accepts: bool = True,
) -> dict[str, Any]:
    base = _base_axis_material(tmp_path, morphism_type="M_T")
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

    proofs: list[dict[str, str]] = [
        write_object(tmp_path, "artifacts/treaty.json", treaty, id_field="treaty_id"),
        write_object(tmp_path, "artifacts/phi_bundle.json", phi_bundle, id_field="translator_bundle_id"),
        write_object(tmp_path, "artifacts/psi_bundle.json", psi_bundle, id_field="translator_bundle_id"),
        write_object(
            tmp_path,
            "artifacts/overlap_object.json",
            {
                "schema_name": "overlap_test_object_v1",
                "schema_version": "v19_0",
                "overlap_object_id": overlap_object_id,
                "object": overlap_object,
            },
        ),
        write_object(
            tmp_path,
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
        proofs.append(
            write_object(
                tmp_path,
                "artifacts/ok_signature.json",
                ok_signature,
                id_field="overlap_signature_id",
            )
        )
    return _axis_bundle(base, proofs)


def test_gate_safe_split_on_treaty_non_total_translator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    axis = _treaty_axis(
        tmp_path,
        phi_ops=[{"op": "TEST", "path": "/missing", "value": 1}],
        include_ok_signature=True,
    )
    with pytest.raises(ContinuityV19Error, match="SAFE_SPLIT:TRANSLATOR_NON_TOTAL"):
        _invoke_gate(tmp_path, axis_bundle=axis)


def test_gate_safe_split_on_treaty_no_new_acceptance_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    axis = _treaty_axis(
        tmp_path,
        phi_ops=[],
        include_ok_signature=True,
        source_accepts=False,
        target_accepts=True,
    )
    with pytest.raises(ContinuityV19Error, match="SAFE_SPLIT:NO_NEW_ACCEPTANCE_PATH"):
        _invoke_gate(tmp_path, axis_bundle=axis)


def test_gate_safe_halt_on_treaty_missing_ok_signature(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    axis = _treaty_axis(
        tmp_path,
        phi_ops=[],
        include_ok_signature=False,
    )
    with pytest.raises(ContinuityV19Error, match="SAFE_HALT"):
        _invoke_gate(tmp_path, axis_bundle=axis)
