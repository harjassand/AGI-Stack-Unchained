from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v19_0.continuity.check_constitution_upgrade_v1 import check_constitution_upgrade
from cdel.v19_0.continuity.check_env_upgrade_v1 import check_env_upgrade
from cdel.v19_0.continuity.check_kernel_upgrade_v1 import check_kernel_upgrade, enforce_kernel_polarity
from cdel.v19_0.continuity.common_v1 import ContinuityV19Error
from cdel.v19_0.tests_continuity.helpers import budget, write_object


def _constitution_payload(required_map: dict[str, list[str]]) -> dict[str, object]:
    return {
        "schema_name": "continuity_constitution_v1",
        "schema_version": "v19_0",
        "constitution_id": "sha256:" + ("0" * 64),
        "admissible_upgrade_types": ["M_H", "M_K", "M_E", "M_C", "M_M"],
        "required_proof_map": required_map,
        "epsilon_terms": {"epsilon_J": 1, "epsilon_udc": 0},
        "debt_amortization_horizons": {"CDL": 1, "CoDL": 1},
        "required_reason_codes": ["SCHEMA_ERROR", "ID_MISMATCH"],
        "safe_policy_defaults": {
            "on_missing_artifact": "SAFE_HALT",
            "on_budget_exhausted": "SAFE_HALT",
            "on_unresolved_overlap": "SAFE_HALT",
        },
        "kernel_polarity_rules": {
            "single_k_plus_required": True,
            "default_other_polarity": "K_MINUS",
        },
    }


def test_two_k_plus_rejected(tmp_path: Path) -> None:
    with pytest.raises(ContinuityV19Error, match="SAFE_HALT"):
        enforce_kernel_polarity([
            {"polarity": "K_PLUS"},
            {"polarity": "K_PLUS"},
        ])


def test_k_plus_without_bootstrap_receipt_safe_halt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    old_kernel = write_object(tmp_path, "artifacts/old_kernel.json", {"kernel": "old"})
    new_kernel = write_object(tmp_path, "artifacts/new_kernel.json", {"kernel": "new"})
    translator = write_object(tmp_path, "artifacts/translator.json", {"translator": "ok"})
    tests_ref = write_object(tmp_path, "artifacts/tests.json", {"tests": "ok"})
    missing_bootstrap = {"artifact_id": "sha256:" + ("1" * 64), "artifact_relpath": "artifacts/missing_bootstrap.json"}

    payload = {
        "schema_name": "kernel_upgrade_v1",
        "schema_version": "v19_0",
        "upgrade_id": "sha256:" + ("0" * 64),
        "old_kernel_ref": old_kernel,
        "new_kernel_ref": new_kernel,
        "bootstrap_receipt_ref": missing_bootstrap,
        "receipt_translator_bundle_ref": translator,
        "determinism_conformance_tests_ref": tests_ref,
        "polarity": "K_PLUS",
        "equivalence_or_extension_proof_ref": None,
    }
    upgrade = write_object(tmp_path, "artifacts/kernel_upgrade.json", payload, id_field="upgrade_id")

    with pytest.raises(ContinuityV19Error, match="SAFE_HALT"):
        check_kernel_upgrade(store_root=tmp_path, kernel_upgrade_ref=upgrade, budget=budget())


def test_env_upgrade_missing_reduction_witness_safe_halt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    old_env = write_object(tmp_path, "artifacts/old_env.json", {"env": "old"})
    new_env = write_object(tmp_path, "artifacts/new_env.json", {"env": "new"})
    envelope = write_object(tmp_path, "artifacts/envelope.json", {"task_answer_pairs": []})

    payload = {
        "schema_name": "env_upgrade_v1",
        "schema_version": "v19_0",
        "upgrade_id": "sha256:" + ("0" * 64),
        "old_env_ref": old_env,
        "new_env_ref": new_env,
        "reduction_witness": {
            "lift": [],
            "proj": [],
            "implication_checks": [],
        },
        "hardness_envelope_ref": envelope,
        "anti_leak_scanner_ref": None,
    }
    upgrade = write_object(tmp_path, "artifacts/env_upgrade_missing.json", payload, id_field="upgrade_id")

    with pytest.raises(ContinuityV19Error, match="SAFE_HALT"):
        check_env_upgrade(store_root=tmp_path, env_upgrade_ref=upgrade, budget=budget())


def test_env_upgrade_implication_breaks_safe_halt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    old_env = write_object(tmp_path, "artifacts/old_env2.json", {"env": "old"})
    new_env = write_object(tmp_path, "artifacts/new_env2.json", {"env": "new"})
    envelope = write_object(tmp_path, "artifacts/envelope2.json", {"task_answer_pairs": []})

    payload = {
        "schema_name": "env_upgrade_v1",
        "schema_version": "v19_0",
        "upgrade_id": "sha256:" + ("0" * 64),
        "old_env_ref": old_env,
        "new_env_ref": new_env,
        "reduction_witness": {
            "lift": [{"old_task_id": "t_old", "new_task_id": "t_new"}],
            "proj": [{"new_answer_id": "a_new", "old_answer_id": "a_old"}],
            "implication_checks": [
                {
                    "lift_task_id": "t_new",
                    "projected_answer_id": "a_old",
                    "implication_holds": False,
                }
            ],
        },
        "hardness_envelope_ref": envelope,
        "anti_leak_scanner_ref": None,
    }
    upgrade = write_object(tmp_path, "artifacts/env_upgrade_bad_implication.json", payload, id_field="upgrade_id")

    with pytest.raises(ContinuityV19Error, match="SAFE_HALT"):
        check_env_upgrade(store_root=tmp_path, env_upgrade_ref=upgrade, budget=budget())


def test_constitution_not_verifiable_by_prior_ck_safe_halt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    old_const = write_object(
        tmp_path,
        "artifacts/old_const.json",
        _constitution_payload({"M_H": ["TRANSLATOR_TOTALITY", "NO_NEW_ACCEPT_PATH"]}),
        id_field="constitution_id",
    )
    new_const = write_object(
        tmp_path,
        "artifacts/new_const_weaker.json",
        _constitution_payload({"M_H": ["TRANSLATOR_TOTALITY"]}),
        id_field="constitution_id",
    )
    ck_profile = write_object(
        tmp_path,
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

    morphism = write_object(
        tmp_path,
        "artifacts/constitution_morphism_bad.json",
        {
            "schema_name": "constitution_morphism_v1",
            "schema_version": "v19_0",
            "morphism_id": "sha256:" + ("0" * 64),
            "old_constitution_ref": old_const,
            "new_constitution_ref": new_const,
            "ck_profile_ref": ck_profile,
            "change_class": "MONOTONE_STRENGTHENING",
            "required_proofs": ["CONSTITUTION_KERNEL_COMPLIANCE"],
            "translator_totality_required": False,
            "constitutional_backrefute_required": False,
        },
        id_field="morphism_id",
    )

    with pytest.raises(ContinuityV19Error, match="SAFE_HALT"):
        check_constitution_upgrade(store_root=tmp_path, constitution_morphism_ref=morphism, budget=budget())


def test_constitution_new_accept_path_without_translation_theorem_safe_halt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    old_const = write_object(
        tmp_path,
        "artifacts/old_const2.json",
        _constitution_payload({"M_H": ["TRANSLATOR_TOTALITY", "NO_NEW_ACCEPT_PATH"]}),
        id_field="constitution_id",
    )
    new_const = write_object(
        tmp_path,
        "artifacts/new_const2.json",
        _constitution_payload({"M_H": ["TRANSLATOR_TOTALITY", "NO_NEW_ACCEPT_PATH"]}),
        id_field="constitution_id",
    )
    ck_profile = write_object(
        tmp_path,
        "artifacts/ck_profile2.json",
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

    morphism = write_object(
        tmp_path,
        "artifacts/constitution_morphism_no_theorem.json",
        {
            "schema_name": "constitution_morphism_v1",
            "schema_version": "v19_0",
            "morphism_id": "sha256:" + ("0" * 64),
            "old_constitution_ref": old_const,
            "new_constitution_ref": new_const,
            "ck_profile_ref": ck_profile,
            "change_class": "CONSERVATIVE_EXTENSION",
            "required_proofs": ["CONSTITUTION_KERNEL_COMPLIANCE"],
            "translator_totality_required": True,
            "constitutional_backrefute_required": False,
        },
        id_field="morphism_id",
    )

    with pytest.raises(ContinuityV19Error, match="SAFE_HALT"):
        check_constitution_upgrade(store_root=tmp_path, constitution_morphism_ref=morphism, budget=budget())
