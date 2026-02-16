from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from cdel.v1_7r.canon import write_canon_json
from cdel.v1_7r.canon import canon_bytes
from cdel.v19_0.continuity.check_continuity_v1 import check_continuity
from cdel.v19_0.continuity.common_v1 import ContinuityV19Error, canon_hash_obj
from cdel.v19_0.omega_promoter_v1 import _verify_axis_bundle_gate
from cdel.v19_0.continuity.objective_J_v1 import compute_J
from cdel.v19_0.tests_continuity.helpers import (
    budget,
    canon_hash,
    make_backrefute_cert,
    make_j_profile,
    make_morphism,
    make_overlap_profile,
    make_regime,
    make_totality_cert,
    make_translator_bundle,
    write_object,
)


def _build_base(tmp_path: Path) -> dict[str, object]:
    old_1 = write_object(tmp_path, "artifacts/old_1.json", {"x": 1})
    old_2 = write_object(tmp_path, "artifacts/old_2.json", {"x": 2})

    old_regime = make_regime(
        tmp_path,
        accepted_artifact_ids=[old_1["artifact_id"], old_2["artifact_id"]],
        prefix="old",
    )
    new_regime = make_regime(
        tmp_path,
        accepted_artifact_ids=[old_1["artifact_id"], old_2["artifact_id"]],
        prefix="new",
    )
    overlap = make_overlap_profile(tmp_path, refs=[old_1, old_2], old_regime=old_regime, new_regime=new_regime)
    translator = make_translator_bundle(tmp_path, ops=[])
    totality = make_totality_cert(
        tmp_path,
        overlap_ref=overlap,
        translator_ref=translator,
        refs=[old_1, old_2],
    )
    morphism = make_morphism(
        tmp_path,
        overlap_ref=overlap,
        translator_ref=translator,
        totality_ref=totality,
        old_regime=old_regime,
        new_regime=new_regime,
    )

    sigma_old = write_object(tmp_path, "artifacts/sigma_old.json", {"invariant_failures": [{"id": 1}]})
    sigma_new = write_object(tmp_path, "artifacts/sigma_new.json", {"invariant_failures": []})

    return {
        "old_1": old_1,
        "old_2": old_2,
        "old_regime": old_regime,
        "new_regime": new_regime,
        "overlap": overlap,
        "translator": translator,
        "totality": totality,
        "morphism": morphism,
        "sigma_old": sigma_old,
        "sigma_new": sigma_new,
    }


def test_continuity_receipt_deterministic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    base = _build_base(tmp_path)

    budgets = {
        "continuity_budget": budget(),
        "translator_budget": budget(),
        "receipt_translation_budget": budget(),
        "totality_budget": budget(),
    }

    r1 = check_continuity(
        sigma_old_ref=base["sigma_old"],
        sigma_new_ref=base["sigma_new"],
        regime_old_ref=base["old_regime"],
        regime_new_ref=base["new_regime"],
        morphism_ref=base["morphism"],
        budgets=budgets,
    )
    r2 = check_continuity(
        sigma_old_ref=base["sigma_old"],
        sigma_new_ref=base["sigma_new"],
        regime_old_ref=base["old_regime"],
        regime_new_ref=base["new_regime"],
        morphism_ref=base["morphism"],
        budgets=budgets,
    )

    assert canon_bytes(r1) == canon_bytes(r2)
    assert r1["final_outcome"] == "ACCEPT"


def test_ordering_does_not_change_acceptance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    base = _build_base(tmp_path)

    reversed_overlap = make_overlap_profile(
        tmp_path,
        refs=[base["old_2"], base["old_1"]],
        old_regime=base["old_regime"],
        new_regime=base["new_regime"],
        relpath="artifacts/overlap_reversed.json",
    )
    reversed_totality = make_totality_cert(
        tmp_path,
        overlap_ref=reversed_overlap,
        translator_ref=base["translator"],
        refs=[base["old_2"], base["old_1"]],
        relpath="artifacts/totality_reversed.json",
    )
    morphism_rev = make_morphism(
        tmp_path,
        overlap_ref=reversed_overlap,
        translator_ref=base["translator"],
        totality_ref=reversed_totality,
        old_regime=base["old_regime"],
        new_regime=base["new_regime"],
        relpath="artifacts/morphism_reversed.json",
    )

    budgets = {
        "continuity_budget": budget(),
        "translator_budget": budget(),
        "receipt_translation_budget": budget(),
        "totality_budget": budget(),
    }

    normal = check_continuity(
        sigma_old_ref=base["sigma_old"],
        sigma_new_ref=base["sigma_new"],
        regime_old_ref=base["old_regime"],
        regime_new_ref=base["new_regime"],
        morphism_ref=base["morphism"],
        budgets=budgets,
    )
    changed = check_continuity(
        sigma_old_ref=base["sigma_old"],
        sigma_new_ref=base["sigma_new"],
        regime_old_ref=base["old_regime"],
        regime_new_ref=base["new_regime"],
        morphism_ref=morphism_rev,
        budgets=budgets,
    )

    assert normal["final_outcome"] == "ACCEPT"
    assert changed["final_outcome"] == "ACCEPT"


def test_missing_overlap_profile_safe_halt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    base = _build_base(tmp_path)

    morphism_payload = {
        "schema_name": "continuity_morphism_v1",
        "schema_version": "v19_0",
        "morphism_id": "sha256:" + ("0" * 64),
        "morphism_type": "M_H",
        "continuity_class": "EXTEND",
        "overlap_profile_ref": {"artifact_id": "sha256:" + ("1" * 64), "artifact_relpath": "artifacts/missing.json"},
        "translator_bundle_ref": base["translator"],
        "optional_projection_ref": None,
        "backrefute_policy": {
            "required": True,
            "allowed_outcomes": ["VALID", "INVALID", "BUDGET_EXHAUSTED"],
            "budget": budget(),
            "policy_on_missing_backrefute": "SAFE_HALT",
        },
        "required_proofs": [
            "TRANSLATOR_TOTALITY",
            "CONTINUITY_CHECK",
            "BACKREFUTE_LANE",
            "NO_NEW_ACCEPT_PATH",
            "REPLAY_DETERMINISM",
            "J_DOMINANCE_RENT_PAID",
        ],
        "budgets": {
            "continuity_budget": budget(),
            "translator_budget": budget(),
            "receipt_translation_budget": budget(),
            "totality_budget": budget(),
        },
        "declared_old_regime_ref": base["old_regime"],
        "declared_new_regime_ref": base["new_regime"],
        "translator_totality_cert_ref": base["totality"],
        "continuity_receipt_ref": None,
        "backrefute_cert_refs": [],
        "explicit_overlap_exceptions": [],
    }
    morphism = write_object(tmp_path, "artifacts/morphism_missing_overlap.json", morphism_payload, id_field="morphism_id")

    budgets = {
        "continuity_budget": budget(),
        "translator_budget": budget(),
        "receipt_translation_budget": budget(),
        "totality_budget": budget(),
    }

    with pytest.raises(ContinuityV19Error, match="SAFE_HALT"):
        check_continuity(
            sigma_old_ref=base["sigma_old"],
            sigma_new_ref=base["sigma_new"],
            regime_old_ref=base["old_regime"],
            regime_new_ref=base["new_regime"],
            morphism_ref=morphism,
            budgets=budgets,
        )


def test_overlap_profile_missing_item_safe_halt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    base = _build_base(tmp_path)

    missing_ref = {
        "artifact_id": "sha256:" + ("e" * 64),
        "artifact_relpath": "artifacts/missing_overlap_item.json",
    }
    overlap = make_overlap_profile(
        tmp_path,
        refs=[base["old_1"], missing_ref],
        old_regime=base["old_regime"],
        new_regime=base["new_regime"],
        relpath="artifacts/overlap_missing_item.json",
    )
    totality = make_totality_cert(
        tmp_path,
        overlap_ref=overlap,
        translator_ref=base["translator"],
        refs=[base["old_1"], missing_ref],
        relpath="artifacts/totality_missing_item.json",
    )
    morphism = make_morphism(
        tmp_path,
        overlap_ref=overlap,
        translator_ref=base["translator"],
        totality_ref=totality,
        old_regime=base["old_regime"],
        new_regime=base["new_regime"],
        relpath="artifacts/morphism_missing_item.json",
    )

    with pytest.raises(ContinuityV19Error, match="SAFE_HALT"):
        check_continuity(
            sigma_old_ref=base["sigma_old"],
            sigma_new_ref=base["sigma_new"],
            regime_old_ref=base["old_regime"],
            regime_new_ref=base["new_regime"],
            morphism_ref=morphism,
            budgets={
                "continuity_budget": budget(),
                "translator_budget": budget(),
                "receipt_translation_budget": budget(),
                "totality_budget": budget(),
            },
        )


def test_overlap_profile_id_mismatch_safe_halt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    base = _build_base(tmp_path)

    bad_overlap_payload = {
        "schema_name": "overlap_profile_v1",
        "schema_version": "v19_0",
        "can_version": "v1_7r",
        "overlap_profile_id": "sha256:" + ("f" * 64),
        "overlap_kind": "ENUMERATED_ACCEPT_SET",
        "declared_overlap_language": {"accepted_artifact_refs": [base["old_1"]]},
        "old_regime_ref": base["old_regime"],
        "new_regime_ref": base["new_regime"],
        "overlap_semantics_profile_ref": write_object(
            tmp_path,
            "artifacts/overlap_semantics_bad.json",
            {
                "schema_name": "local_overlap_semantics_profile_v1",
                "schema_version": "v19_0",
                "semantics_profile_id": "sha256:" + ("0" * 64),
                "semantics_kind": "LOCAL_ENUMERATED_ACCEPT_SET",
                "acceptance_checker_kind": "ENUMERATED_ACCEPT_SET",
            },
            id_field="semantics_profile_id",
        ),
    }
    bad_overlap_ref = write_object(tmp_path, "artifacts/overlap_bad_id.json", bad_overlap_payload)
    morphism = make_morphism(
        tmp_path,
        overlap_ref=bad_overlap_ref,
        translator_ref=base["translator"],
        totality_ref=base["totality"],
        old_regime=base["old_regime"],
        new_regime=base["new_regime"],
        relpath="artifacts/morphism_bad_overlap_id.json",
    )

    with pytest.raises(ContinuityV19Error, match="SAFE_HALT"):
        check_continuity(
            sigma_old_ref=base["sigma_old"],
            sigma_new_ref=base["sigma_new"],
            regime_old_ref=base["old_regime"],
            regime_new_ref=base["new_regime"],
            morphism_ref=morphism,
            budgets={
                "continuity_budget": budget(),
                "translator_budget": budget(),
                "receipt_translation_budget": budget(),
                "totality_budget": budget(),
            },
        )


def test_overlap_can_version_mismatch_safe_halt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    base = _build_base(tmp_path)
    overlap_path = Path(base["overlap"]["artifact_relpath"])
    payload = {
        "schema_name": "overlap_profile_v1",
        "schema_version": "v19_0",
        "can_version": "v0_bad",
        "overlap_profile_id": "sha256:" + ("0" * 64),
        "overlap_kind": "ENUMERATED_ACCEPT_SET",
        "declared_overlap_language": {"accepted_artifact_refs": [base["old_1"], base["old_2"]]},
        "old_regime_ref": base["old_regime"],
        "new_regime_ref": base["new_regime"],
        "overlap_semantics_profile_ref": write_object(
            tmp_path,
            "artifacts/overlap_semantics_version_bad.json",
            {
                "schema_name": "local_overlap_semantics_profile_v1",
                "schema_version": "v19_0",
                "semantics_profile_id": "sha256:" + ("0" * 64),
                "semantics_kind": "LOCAL_ENUMERATED_ACCEPT_SET",
                "acceptance_checker_kind": "ENUMERATED_ACCEPT_SET",
            },
            id_field="semantics_profile_id",
        ),
    }
    # Preserve canonical id field binding but inject an invalid can_version in a new artifact.
    payload_no_id = dict(payload)
    payload_no_id.pop("overlap_profile_id", None)
    payload["overlap_profile_id"] = canon_hash(payload_no_id)
    write_canon_json(overlap_path, payload)
    bad_overlap_ref = {"artifact_id": canon_hash(payload), "artifact_relpath": base["overlap"]["artifact_relpath"]}
    morphism = make_morphism(
        tmp_path,
        overlap_ref=bad_overlap_ref,
        translator_ref=base["translator"],
        totality_ref=base["totality"],
        old_regime=base["old_regime"],
        new_regime=base["new_regime"],
        relpath="artifacts/morphism_bad_can_version.json",
    )

    with pytest.raises(ContinuityV19Error, match="SAFE_HALT"):
        check_continuity(
            sigma_old_ref=base["sigma_old"],
            sigma_new_ref=base["sigma_new"],
            regime_old_ref=base["old_regime"],
            regime_new_ref=base["new_regime"],
            morphism_ref=morphism,
            budgets={
                "continuity_budget": budget(),
                "translator_budget": budget(),
                "receipt_translation_budget": budget(),
                "totality_budget": budget(),
            },
        )


def test_invalid_translator_and_budget_exhaustion_safe_halt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    base = _build_base(tmp_path)

    bad_translator = make_translator_bundle(
        tmp_path,
        ops=[
            {"op": "REPLACE", "path": "/missing", "value": 7},
            {"op": "ADD", "path": "/y", "value": 9},
        ],
        relpath="artifacts/translator_bad.json",
    )
    bad_totality = make_totality_cert(
        tmp_path,
        overlap_ref=base["overlap"],
        translator_ref=bad_translator,
        refs=[base["old_1"], base["old_2"]],
        relpath="artifacts/totality_bad_translator.json",
    )
    morphism = make_morphism(
        tmp_path,
        overlap_ref=base["overlap"],
        translator_ref=bad_translator,
        totality_ref=bad_totality,
        old_regime=base["old_regime"],
        new_regime=base["new_regime"],
        relpath="artifacts/morphism_bad_translator.json",
    )

    low_budget = budget(max_steps=1)
    budgets = {
        "continuity_budget": budget(),
        "translator_budget": low_budget,
        "receipt_translation_budget": budget(),
        "totality_budget": budget(),
    }
    receipt = check_continuity(
        sigma_old_ref=base["sigma_old"],
        sigma_new_ref=base["sigma_new"],
        regime_old_ref=base["old_regime"],
        regime_new_ref=base["new_regime"],
        morphism_ref=morphism,
        budgets=budgets,
    )
    assert receipt["final_outcome"] == "SAFE_HALT"


def test_no_new_acceptance_path_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    base = _build_base(tmp_path)

    translated_payload = {"x": 1, "y": 7}
    translated_id = canon_hash(translated_payload)
    morphing_translator = make_translator_bundle(
        tmp_path,
        ops=[{"op": "ADD", "path": "/y", "value": 7}],
        relpath="artifacts/translator_teleport.json",
    )

    regime_new = make_regime(
        tmp_path,
        accepted_artifact_ids=[translated_id, base["old_1"]["artifact_id"]],
        prefix="new_teleport",
    )
    overlap = make_overlap_profile(
        tmp_path,
        refs=[base["old_1"]],
        old_regime=base["old_regime"],
        new_regime=regime_new,
        relpath="artifacts/overlap_teleport.json",
    )
    totality = make_totality_cert(
        tmp_path,
        overlap_ref=overlap,
        translator_ref=morphing_translator,
        refs=[base["old_1"]],
        relpath="artifacts/totality_teleport.json",
    )
    morphism = make_morphism(
        tmp_path,
        overlap_ref=overlap,
        translator_ref=morphing_translator,
        totality_ref=totality,
        old_regime=base["old_regime"],
        new_regime=regime_new,
        relpath="artifacts/morphism_teleport.json",
    )

    receipt = check_continuity(
        sigma_old_ref=base["sigma_old"],
        sigma_new_ref=base["sigma_new"],
        regime_old_ref=base["old_regime"],
        regime_new_ref=regime_new,
        morphism_ref=morphism,
        budgets={
            "continuity_budget": budget(),
            "translator_budget": budget(),
            "receipt_translation_budget": budget(),
            "totality_budget": budget(),
        },
    )
    assert receipt["final_outcome"] == "SAFE_HALT"


def test_backrefute_required_when_translation_rejects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    base = _build_base(tmp_path)

    # New regime accepts nothing from overlap, forcing backrefute path.
    rejecting_regime = make_regime(tmp_path, accepted_artifact_ids=[], prefix="new_reject")
    overlap = make_overlap_profile(
        tmp_path,
        refs=[base["old_1"]],
        old_regime=base["old_regime"],
        new_regime=rejecting_regime,
        relpath="artifacts/overlap_backrefute.json",
    )
    overlap_totality = make_totality_cert(
        tmp_path,
        overlap_ref=overlap,
        translator_ref=base["translator"],
        refs=[base["old_1"]],
        relpath="artifacts/totality_backrefute.json",
    )

    missing_backrefute_morphism = make_morphism(
        tmp_path,
        overlap_ref=overlap,
        translator_ref=base["translator"],
        totality_ref=overlap_totality,
        old_regime=base["old_regime"],
        new_regime=rejecting_regime,
        backrefute_refs=[],
        relpath="artifacts/morphism_missing_backrefute.json",
    )
    receipt = check_continuity(
        sigma_old_ref=base["sigma_old"],
        sigma_new_ref=base["sigma_new"],
        regime_old_ref=base["old_regime"],
        regime_new_ref=rejecting_regime,
        morphism_ref=missing_backrefute_morphism,
        budgets={
            "continuity_budget": budget(),
            "translator_budget": budget(),
            "receipt_translation_budget": budget(),
            "totality_budget": budget(),
        },
    )
    assert receipt["final_outcome"] == "SAFE_HALT"

    good_backrefute = make_backrefute_cert(
        tmp_path,
        old_regime=base["old_regime"],
        target_ref=base["old_1"],
        result="VALID",
        relpath="artifacts/backrefute_good.json",
    )
    with_backrefute_morphism = make_morphism(
        tmp_path,
        overlap_ref=overlap,
        translator_ref=base["translator"],
        totality_ref=overlap_totality,
        old_regime=base["old_regime"],
        new_regime=rejecting_regime,
        backrefute_refs=[good_backrefute],
        relpath="artifacts/morphism_with_backrefute.json",
    )
    receipt_ok = check_continuity(
        sigma_old_ref=base["sigma_old"],
        sigma_new_ref=base["sigma_new"],
        regime_old_ref=base["old_regime"],
        regime_new_ref=rejecting_regime,
        morphism_ref=with_backrefute_morphism,
        budgets={
            "continuity_budget": budget(),
            "translator_budget": budget(),
            "receipt_translation_budget": budget(),
            "totality_budget": budget(),
        },
    )
    assert receipt_ok["final_outcome"] == "ACCEPT"


def test_compute_j_deterministic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    sigma = write_object(tmp_path, "artifacts/sigma.json", {"invariant_failures": [{"id": 1}, {"id": 2}]})
    regime = make_regime(tmp_path, accepted_artifact_ids=[], prefix="j")
    profile = make_j_profile(tmp_path)

    j1 = compute_J(regime_ref=regime, sigma_ref=sigma, profile_ref=profile, budgets=budget())
    j2 = compute_J(regime_ref=regime, sigma_ref=sigma, profile_ref=profile, budgets=budget())
    assert canon_bytes(j1) == canon_bytes(j2)


def test_meta_core_precheck_blocks_missing_continuity_receipt(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle"
    (bundle_dir / "omega").mkdir(parents=True)

    sigma_old = write_object(bundle_dir, "omega/sigma_old.json", {"state": "old"})
    sigma_new = write_object(bundle_dir, "omega/sigma_new.json", {"state": "new"})
    profile = make_j_profile(bundle_dir, relpath="omega/j_profile.json")
    regime_old = make_regime(bundle_dir, accepted_artifact_ids=[], prefix="bundle_old")
    regime_new = make_regime(bundle_dir, accepted_artifact_ids=[], prefix="bundle_new")

    axis_wo_id = {
        "schema_name": "axis_upgrade_bundle_v1",
        "schema_version": "v19_0",
        "sigma_old_ref": sigma_old,
        "sigma_new_ref": sigma_new,
        "regime_old_ref": regime_old,
        "regime_new_ref": regime_new,
        "objective_J_profile_ref": profile,
        "continuity_budget": budget(),
        "governed_surfaces_touched": ["C", "K"],
        "morphisms": [
            {
                "morphism_ref": write_object(bundle_dir, "omega/morphism.json", {"x": 1}),
                "overlap_profile_ref": write_object(bundle_dir, "omega/overlap.json", {"x": 2}),
                "translator_bundle_ref": write_object(bundle_dir, "omega/translator.json", {"x": 3}),
                "totality_cert_ref": write_object(bundle_dir, "omega/totality.json", {"x": 4}),
                "continuity_receipt_ref": {"artifact_id": "sha256:" + ("a" * 64), "artifact_relpath": "omega/missing_continuity.json"},
                "axis_specific_proof_refs": [],
            }
        ],
    }
    axis = dict(axis_wo_id)
    axis["axis_bundle_id"] = canon_hash(axis_wo_id)
    write_object(bundle_dir, "omega/axis_upgrade_bundle_v1.json", axis)

    module_path = Path(__file__).resolve().parents[4] / "meta-core" / "kernel" / "verify_promotion_bundle.py"
    spec = importlib.util.spec_from_file_location("verify_promotion_bundle_module", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    with pytest.raises(RuntimeError, match="CONTINUITY_MISSING_ARTIFACT"):
        module._enforce_continuity_sidecar(bundle_dir)


def test_non_replayable_continuity_receipt_falsifier(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    base = _build_base(tmp_path)
    j_profile = make_j_profile(tmp_path, relpath="artifacts/j_profile_for_gate.json")

    budgets = {
        "continuity_budget": budget(),
        "translator_budget": budget(),
        "receipt_translation_budget": budget(),
        "totality_budget": budget(),
    }
    recomputed = check_continuity(
        sigma_old_ref=base["sigma_old"],
        sigma_new_ref=base["sigma_new"],
        regime_old_ref=base["old_regime"],
        regime_new_ref=base["new_regime"],
        morphism_ref=base["morphism"],
        budgets=budgets,
    )
    tampered = dict(recomputed)
    tampered_items = list(tampered.get("items", []))
    assert tampered_items
    tampered_first = dict(tampered_items[0])
    tampered_first["translation_acceptance"] = "REJECT"
    tampered_items[0] = tampered_first
    tampered["items"] = tampered_items
    bad_receipt_ref = write_object(
        tmp_path,
        "artifacts/continuity_receipt_tampered.json",
        tampered,
        id_field="receipt_id",
    )

    axis_wo_id = {
        "schema_name": "axis_upgrade_bundle_v1",
        "schema_version": "v19_0",
        "sigma_old_ref": base["sigma_old"],
        "sigma_new_ref": base["sigma_new"],
        "regime_old_ref": base["old_regime"],
        "regime_new_ref": base["new_regime"],
        "objective_J_profile_ref": j_profile,
        "continuity_budget": budget(),
        "morphisms": [
            {
                "morphism_ref": base["morphism"],
                "overlap_profile_ref": base["overlap"],
                "translator_bundle_ref": base["translator"],
                "totality_cert_ref": base["totality"],
                "continuity_receipt_ref": bad_receipt_ref,
                "axis_specific_proof_refs": [],
            }
        ],
    }
    axis = dict(axis_wo_id)
    axis["axis_bundle_id"] = canon_hash(axis_wo_id)

    bundle_dir = tmp_path / "promo_bundle"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    bundle_obj = {"touched_paths": ["meta-core/kernel/verify_promotion_bundle.py"]}
    bundle_path = bundle_dir / "bundle.json"
    write_canon_json(bundle_path, bundle_obj)
    write_canon_json(bundle_dir / "axis_upgrade_bundle_v1.json", axis)
    promotion_dir = tmp_path / "promotion"
    promotion_dir.mkdir(parents=True, exist_ok=True)

    with pytest.raises(ContinuityV19Error, match="SAFE_HALT"):
        _verify_axis_bundle_gate(
            bundle_obj=bundle_obj,
            bundle_path=bundle_path,
            promotion_dir=promotion_dir,
        )
