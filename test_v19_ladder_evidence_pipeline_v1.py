from __future__ import annotations

import shutil
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "CDEL-v2") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "CDEL-v2"))


def _load_pipeline_module():
    module_path = REPO_ROOT / "tools" / "v19_runs" / "v19_ladder_evidence_pipeline_v1.py"
    spec = importlib.util.spec_from_file_location("v19_ladder_evidence_pipeline_module", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"unable to load module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_v19_ladder_evidence_pipeline_passes_and_counts_gate_failures(tmp_path: Path) -> None:
    from cdel.v1_7r.canon import hash_json as canon_hash_obj
    from cdel.v1_7r.canon import write_canon_json
    from cdel.v18_0.omega_common_v1 import write_hashed_json
    from cdel.v19_0.common_v1 import validate_schema as validate_schema_v19

    runs_root = tmp_path / "runs"
    tick_dir = runs_root / "tick_0001"
    state_root = tick_dir / "daemon" / "rsi_omega_daemon_v19_0" / "state"

    # Common sha placeholders.
    Z = "sha256:" + ("0" * 64)
    O = "sha256:" + ("1" * 64)

    def _mk_dispatch(*, dispatch_id: str, tick_u64: int, promoted: bool, gate_failure: bool) -> None:
        dispatch_dir = state_root / "dispatch" / dispatch_id
        verifier_dir = dispatch_dir / "verifier"
        promo_dir = dispatch_dir / "promotion"
        activation_dir = dispatch_dir / "activation"

        subrun_root_rel = f"subruns/{dispatch_id}"
        state_dir_rel = "state"
        subrun_state_dir = state_root / subrun_root_rel / state_dir_rel
        subrun_promotion_dir = subrun_state_dir / "promotion"

        # Dispatch receipt.
        dispatch_payload = {
            "schema_version": "omega_dispatch_receipt_v1",
            "tick_u64": int(tick_u64),
            "campaign_id": "campaign_x",
            "capability_id": "cap_x",
            "invocation": {
                "py_module": "module_x",
                "argv": ["--flag"],
                "env_fingerprint_hash": Z,
            },
            "subrun": {
                "subrun_root_rel": subrun_root_rel,
                "state_dir_rel": state_dir_rel,
                "subrun_tree_hash": Z,
            },
            "stdout_hash": Z,
            "stderr_hash": Z,
            "return_code": 0,
        }
        write_hashed_json(dispatch_dir, "omega_dispatch_receipt_v1.json", dispatch_payload, id_field="receipt_id")

        # Subverifier receipt (not required by ladder pipeline, but matches real runs).
        subverifier_payload = {
            "schema_version": "omega_subverifier_receipt_v1",
            "tick_u64": int(tick_u64),
            "campaign_id": "campaign_x",
            "verifier_module": "verifier_x",
            "verifier_mode": "full",
            "state_dir_hash": Z,
            "replay_repo_root_rel": None,
            "replay_repo_root_hash": None,
            "result": {"status": "VALID", "reason_code": None},
            "stdout_hash": Z,
            "stderr_hash": Z,
        }
        _, sub_obj, _ = write_hashed_json(
            verifier_dir, "omega_subverifier_receipt_v1.json", subverifier_payload, id_field="receipt_id"
        )

        promotion_bundle_hash = "sha256:" + ("2" * 64)
        promotion_status = "PROMOTED" if promoted else "REJECTED"
        promotion_reason = None if promoted else "UNKNOWN"

        promotion_payload = {
            "schema_version": "omega_promotion_receipt_v1",
            "tick_u64": int(tick_u64),
            "promotion_bundle_hash": promotion_bundle_hash,
            "meta_core_verifier_fingerprint": {
                "constitution_meta_hash": "meta_x",
                "binary_hash_or_build_id": "build_x",
            },
            "result": {"status": promotion_status, "reason_code": promotion_reason},
            "active_manifest_hash_after": None,
        }
        write_hashed_json(promo_dir, "omega_promotion_receipt_v1.json", promotion_payload, id_field="receipt_id")

        if gate_failure:
            write_canon_json(
                subrun_promotion_dir / "axis_gate_failure_v1.json",
                {
                    "schema_name": "axis_gate_failure_v1",
                    "schema_version": "v19_0",
                    "outcome": "SAFE_SPLIT",
                    # SHOULD start with SAFE_SPLIT:, but is not required.
                    "detail": "split without prefix",
                },
            )

        if not promoted:
            return

        meta_verify_payload = {
            "schema_version": "meta_core_promo_verify_receipt_v1",
            "return_code": 0,
            "stdout_hash": Z,
            "stderr_hash": Z,
            "verifier_out_hash": Z,
            "pass": True,
        }
        _, meta_obj, _ = write_hashed_json(promo_dir, "meta_core_promo_verify_receipt_v1.json", meta_verify_payload)

        binding_without_id = {
            "schema_version": "omega_activation_binding_v1",
            "tick_u64": int(tick_u64),
            "campaign_id": "campaign_x",
            "capability_id": "cap_x",
            "promotion_bundle_hash": promotion_bundle_hash,
            "activation_key": "key_x",
            "source_run_root_rel": tick_dir.name,
            "subverifier_receipt_hash": canon_hash_obj(sub_obj),
            "meta_core_promo_verify_receipt_hash": canon_hash_obj(meta_obj),
        }
        binding_payload = dict(binding_without_id)
        binding_payload["binding_id"] = canon_hash_obj(binding_without_id)
        write_canon_json(promo_dir / "omega_activation_binding_v1.json", binding_payload)

        activation_payload = {
            "schema_version": "omega_activation_receipt_v1",
            "tick_u64": int(tick_u64),
            "before_active_manifest_hash": Z,
            "after_active_manifest_hash": O,
            "healthcheck_suite_hash": Z,
            "healthcheck_result": "PASS",
            "activation_method": "ATOMIC_POINTER_SWAP",
            "activation_success": True,
            "pass": True,
            "reasons": ["HEALTHCHECK_PASS"],
        }
        write_hashed_json(activation_dir, "omega_activation_receipt_v1.json", activation_payload, id_field="receipt_id")

        # Gate check emits objective snapshots into the subrun promotion dir.
        write_canon_json(subrun_promotion_dir / "objective_J_old_v1.json", {"weighted_sum": 10, "epsilon": 0, "terms": {}})
        write_canon_json(subrun_promotion_dir / "objective_J_new_v1.json", {"weighted_sum": 5, "epsilon": 0, "terms": {}})

        # Axis bundle + morphism artifact inside dispatch promotion dir.
        bundle_root = promo_dir / "meta_core_promotion_bundle_v1"
        axis_dir = bundle_root / "omega"
        morphism_rel = "omega/morphisms/m1.json"
        write_canon_json(bundle_root / morphism_rel, {"morphism_type": "M_SIGMA"})
        morphism_id = canon_hash_obj({"morphism_type": "M_SIGMA"})

        ref = lambda rel: {"artifact_id": Z, "artifact_relpath": rel}
        regime = {"C": ref("omega/C.json"), "K": ref("omega/K.json"), "E": ref("omega/E.json"), "W": ref("omega/W.json"), "T": ref("omega/T.json")}
        axis_without_id = {
            "schema_name": "axis_upgrade_bundle_v1",
            "schema_version": "v19_0",
            "sigma_old_ref": ref("omega/sigma_old.json"),
            "sigma_new_ref": ref("omega/sigma_new.json"),
            "regime_old_ref": regime,
            "regime_new_ref": regime,
            "objective_J_profile_ref": ref("omega/objective_J_profile.json"),
            "continuity_budget": {
                "schema_name": "budget_spec_v1",
                "schema_version": "v19_0",
                "max_steps": 1,
                "max_bytes_read": 0,
                "max_bytes_write": 0,
                "max_items": 1,
                "seed": 0,
                "policy": "SAFE_HALT",
            },
            "morphisms": [
                {
                    "morphism_ref": {"artifact_id": morphism_id, "artifact_relpath": morphism_rel},
                    "overlap_profile_ref": ref("omega/overlap.json"),
                    "translator_bundle_ref": ref("omega/translator.json"),
                    "totality_cert_ref": ref("omega/totality.json"),
                    "continuity_receipt_ref": ref("omega/continuity.json"),
                    "axis_specific_proof_refs": [ref("omega/proof.json")],
                }
            ],
        }
        axis_payload = dict(axis_without_id)
        axis_payload["axis_bundle_id"] = canon_hash_obj(axis_without_id)
        write_canon_json(axis_dir / "axis_upgrade_bundle_v1.json", axis_payload)

    # One successful promotion and one rejected tick with a SAFE_SPLIT gate failure whose detail
    # does NOT start with \"SAFE_SPLIT:\" (allowed: directive marks this as SHOULD, not MUST).
    _mk_dispatch(dispatch_id="dispatch_0001", tick_u64=1, promoted=True, gate_failure=False)
    _mk_dispatch(dispatch_id="dispatch_0002", tick_u64=1, promoted=False, gate_failure=True)

    module = _load_pipeline_module()
    report, fatal_failures, nonfatal_failures = module._build_report(runs_root=runs_root)
    assert fatal_failures == []
    assert nonfatal_failures == []
    assert report["proof_status"] == "PASS"
    assert report["axis_gate_failures"]["by_outcome_u64"]["SAFE_SPLIT"] == 1
    assert report["morphism_stats"]["morphism_types_promoted"] == ["M_SIGMA"]

    # Schema validation for the report itself.
    validate_schema_v19(report, "v19_ladder_evidence_report_v1")

    # No absolute paths in the evidence manifest.
    for row in report["inputs_manifest"]:
        relpath = str(row["relpath"])
        assert relpath and not relpath.startswith("/")
        assert "\\" not in relpath


def test_v19_ladder_evidence_pipeline_is_deterministic_and_relocatable(tmp_path: Path) -> None:
    from cdel.v1_7r.canon import canon_bytes
    from cdel.v1_7r.canon import hash_json as canon_hash_obj
    from cdel.v1_7r.canon import write_canon_json
    from cdel.v18_0.omega_common_v1 import write_hashed_json

    runs_root = tmp_path / "runs"
    tick_dir = runs_root / "tick_0001"
    state_root = tick_dir / "daemon" / "rsi_omega_daemon_v19_0" / "state"

    Z = "sha256:" + ("0" * 64)
    O = "sha256:" + ("1" * 64)
    promotion_bundle_hash = "sha256:" + ("2" * 64)

    dispatch_id = "dispatch_0001"
    dispatch_dir = state_root / "dispatch" / dispatch_id
    promo_dir = dispatch_dir / "promotion"
    activation_dir = dispatch_dir / "activation"

    subrun_root_rel = f"subruns/{dispatch_id}"
    state_dir_rel = "state"
    subrun_state_dir = state_root / subrun_root_rel / state_dir_rel
    subrun_promotion_dir = subrun_state_dir / "promotion"

    dispatch_payload = {
        "schema_version": "omega_dispatch_receipt_v1",
        "tick_u64": 1,
        "campaign_id": "campaign_x",
        "capability_id": "cap_x",
        "invocation": {"py_module": "module_x", "argv": [], "env_fingerprint_hash": Z},
        "subrun": {"subrun_root_rel": subrun_root_rel, "state_dir_rel": state_dir_rel, "subrun_tree_hash": Z},
        "stdout_hash": Z,
        "stderr_hash": Z,
        "return_code": 0,
    }
    write_hashed_json(dispatch_dir, "omega_dispatch_receipt_v1.json", dispatch_payload, id_field="receipt_id")

    promotion_payload = {
        "schema_version": "omega_promotion_receipt_v1",
        "tick_u64": 1,
        "promotion_bundle_hash": promotion_bundle_hash,
        "meta_core_verifier_fingerprint": {"constitution_meta_hash": "meta_x", "binary_hash_or_build_id": "build_x"},
        "result": {"status": "PROMOTED", "reason_code": None},
        "active_manifest_hash_after": None,
    }
    write_hashed_json(promo_dir, "omega_promotion_receipt_v1.json", promotion_payload, id_field="receipt_id")

    meta_verify_payload = {
        "schema_version": "meta_core_promo_verify_receipt_v1",
        "return_code": 0,
        "stdout_hash": Z,
        "stderr_hash": Z,
        "verifier_out_hash": Z,
        "pass": True,
    }
    _, meta_obj, _ = write_hashed_json(promo_dir, "meta_core_promo_verify_receipt_v1.json", meta_verify_payload)

    binding_without_id = {
        "schema_version": "omega_activation_binding_v1",
        "tick_u64": 1,
        "campaign_id": "campaign_x",
        "capability_id": "cap_x",
        "promotion_bundle_hash": promotion_bundle_hash,
        "activation_key": "key_x",
        "source_run_root_rel": tick_dir.name,
        "subverifier_receipt_hash": Z,
        "meta_core_promo_verify_receipt_hash": canon_hash_obj(meta_obj),
    }
    binding_payload = dict(binding_without_id)
    binding_payload["binding_id"] = canon_hash_obj(binding_without_id)
    write_canon_json(promo_dir / "omega_activation_binding_v1.json", binding_payload)

    activation_payload = {
        "schema_version": "omega_activation_receipt_v1",
        "tick_u64": 1,
        "before_active_manifest_hash": Z,
        "after_active_manifest_hash": O,
        "healthcheck_suite_hash": Z,
        "healthcheck_result": "PASS",
        "activation_method": "ATOMIC_POINTER_SWAP",
        "activation_success": True,
        "pass": True,
        "reasons": ["HEALTHCHECK_PASS"],
    }
    write_hashed_json(activation_dir, "omega_activation_receipt_v1.json", activation_payload, id_field="receipt_id")

    write_canon_json(subrun_promotion_dir / "objective_J_old_v1.json", {"weighted_sum": 10, "epsilon": 0, "terms": {}})
    write_canon_json(subrun_promotion_dir / "objective_J_new_v1.json", {"weighted_sum": 5, "epsilon": 0, "terms": {}})

    bundle_root = promo_dir / "meta_core_promotion_bundle_v1"
    axis_dir = bundle_root / "omega"
    morphism_rel = "omega/morphisms/m1.json"
    write_canon_json(bundle_root / morphism_rel, {"morphism_type": "M_SIGMA"})
    morphism_id = canon_hash_obj({"morphism_type": "M_SIGMA"})
    ref = lambda rel: {"artifact_id": Z, "artifact_relpath": rel}
    regime = {
        "C": ref("omega/C.json"),
        "K": ref("omega/K.json"),
        "E": ref("omega/E.json"),
        "W": ref("omega/W.json"),
        "T": ref("omega/T.json"),
    }
    axis_without_id = {
        "schema_name": "axis_upgrade_bundle_v1",
        "schema_version": "v19_0",
        "sigma_old_ref": ref("omega/sigma_old.json"),
        "sigma_new_ref": ref("omega/sigma_new.json"),
        "regime_old_ref": regime,
        "regime_new_ref": regime,
        "objective_J_profile_ref": ref("omega/objective_J_profile.json"),
        "continuity_budget": {
            "schema_name": "budget_spec_v1",
            "schema_version": "v19_0",
            "max_steps": 1,
            "max_bytes_read": 0,
            "max_bytes_write": 0,
            "max_items": 1,
            "seed": 0,
            "policy": "SAFE_HALT",
        },
        "morphisms": [
            {
                "morphism_ref": {"artifact_id": morphism_id, "artifact_relpath": morphism_rel},
                "overlap_profile_ref": ref("omega/overlap.json"),
                "translator_bundle_ref": ref("omega/translator.json"),
                "totality_cert_ref": ref("omega/totality.json"),
                "continuity_receipt_ref": ref("omega/continuity.json"),
                "axis_specific_proof_refs": [ref("omega/proof.json")],
            }
        ],
    }
    axis_payload = dict(axis_without_id)
    axis_payload["axis_bundle_id"] = canon_hash_obj(axis_without_id)
    write_canon_json(axis_dir / "axis_upgrade_bundle_v1.json", axis_payload)

    module = _load_pipeline_module()
    report1, fatal1, nonfatal1 = module._build_report(runs_root=runs_root)
    assert report1["proof_status"] == "PASS"
    assert fatal1 == []
    assert nonfatal1 == []

    report2, fatal2, nonfatal2 = module._build_report(runs_root=runs_root)
    assert report2["proof_status"] == "PASS"
    assert fatal2 == []
    assert nonfatal2 == []
    assert canon_bytes(report2) == canon_bytes(report1)

    relocated_root = tmp_path / "relocated"
    shutil.copytree(runs_root, relocated_root)
    report3, fatal3, nonfatal3 = module._build_report(runs_root=relocated_root)
    assert report3["proof_status"] == "PASS"
    assert fatal3 == []
    assert nonfatal3 == []
    assert canon_bytes(report3) == canon_bytes(report1)


def test_v19_ladder_evidence_pipeline_fails_closed_on_hash_mismatch(tmp_path: Path) -> None:
    from cdel.v1_7r.canon import hash_json as canon_hash_obj
    from cdel.v1_7r.canon import write_canon_json
    from cdel.v18_0.omega_common_v1 import write_hashed_json

    runs_root = tmp_path / "runs"
    tick_dir = runs_root / "tick_0001"
    state_root = tick_dir / "daemon" / "rsi_omega_daemon_v19_0" / "state"

    Z = "sha256:" + ("0" * 64)
    O = "sha256:" + ("1" * 64)
    promotion_bundle_hash = "sha256:" + ("2" * 64)

    dispatch_id = "dispatch_0001"
    dispatch_dir = state_root / "dispatch" / dispatch_id
    promo_dir = dispatch_dir / "promotion"
    activation_dir = dispatch_dir / "activation"

    subrun_root_rel = f"subruns/{dispatch_id}"
    state_dir_rel = "state"
    subrun_state_dir = state_root / subrun_root_rel / state_dir_rel
    subrun_promotion_dir = subrun_state_dir / "promotion"

    dispatch_payload = {
        "schema_version": "omega_dispatch_receipt_v1",
        "tick_u64": 1,
        "campaign_id": "campaign_x",
        "capability_id": "cap_x",
        "invocation": {"py_module": "module_x", "argv": [], "env_fingerprint_hash": Z},
        "subrun": {"subrun_root_rel": subrun_root_rel, "state_dir_rel": state_dir_rel, "subrun_tree_hash": Z},
        "stdout_hash": Z,
        "stderr_hash": Z,
        "return_code": 0,
    }
    write_hashed_json(dispatch_dir, "omega_dispatch_receipt_v1.json", dispatch_payload, id_field="receipt_id")

    promotion_payload = {
        "schema_version": "omega_promotion_receipt_v1",
        "tick_u64": 1,
        "promotion_bundle_hash": promotion_bundle_hash,
        "meta_core_verifier_fingerprint": {"constitution_meta_hash": "meta_x", "binary_hash_or_build_id": "build_x"},
        "result": {"status": "PROMOTED", "reason_code": None},
        "active_manifest_hash_after": None,
    }
    write_hashed_json(promo_dir, "omega_promotion_receipt_v1.json", promotion_payload, id_field="receipt_id")

    meta_verify_payload = {
        "schema_version": "meta_core_promo_verify_receipt_v1",
        "return_code": 0,
        "stdout_hash": Z,
        "stderr_hash": Z,
        "verifier_out_hash": Z,
        "pass": True,
    }
    _, meta_obj, _ = write_hashed_json(promo_dir, "meta_core_promo_verify_receipt_v1.json", meta_verify_payload)

    binding_without_id = {
        "schema_version": "omega_activation_binding_v1",
        "tick_u64": 1,
        "campaign_id": "campaign_x",
        "capability_id": "cap_x",
        "promotion_bundle_hash": promotion_bundle_hash,
        "activation_key": "key_x",
        "source_run_root_rel": tick_dir.name,
        "subverifier_receipt_hash": Z,
        "meta_core_promo_verify_receipt_hash": canon_hash_obj(meta_obj),
    }
    binding_payload = dict(binding_without_id)
    binding_payload["binding_id"] = canon_hash_obj(binding_without_id)
    write_canon_json(promo_dir / "omega_activation_binding_v1.json", binding_payload)

    activation_payload = {
        "schema_version": "omega_activation_receipt_v1",
        "tick_u64": 1,
        "before_active_manifest_hash": Z,
        "after_active_manifest_hash": O,
        "healthcheck_suite_hash": Z,
        "healthcheck_result": "PASS",
        "activation_method": "ATOMIC_POINTER_SWAP",
        "activation_success": True,
        "pass": True,
        "reasons": ["HEALTHCHECK_PASS"],
    }
    write_hashed_json(activation_dir, "omega_activation_receipt_v1.json", activation_payload, id_field="receipt_id")

    write_canon_json(subrun_promotion_dir / "objective_J_old_v1.json", {"weighted_sum": 10, "epsilon": 0, "terms": {}})
    write_canon_json(subrun_promotion_dir / "objective_J_new_v1.json", {"weighted_sum": 5, "epsilon": 0, "terms": {}})

    bundle_root = promo_dir / "meta_core_promotion_bundle_v1"
    axis_dir = bundle_root / "omega"
    morphism_rel = "omega/morphisms/m1.json"
    write_canon_json(bundle_root / morphism_rel, {"morphism_type": "M_SIGMA"})
    morphism_id = canon_hash_obj({"morphism_type": "M_SIGMA"})
    ref = lambda rel: {"artifact_id": Z, "artifact_relpath": rel}
    regime = {
        "C": ref("omega/C.json"),
        "K": ref("omega/K.json"),
        "E": ref("omega/E.json"),
        "W": ref("omega/W.json"),
        "T": ref("omega/T.json"),
    }
    axis_without_id = {
        "schema_name": "axis_upgrade_bundle_v1",
        "schema_version": "v19_0",
        "sigma_old_ref": ref("omega/sigma_old.json"),
        "sigma_new_ref": ref("omega/sigma_new.json"),
        "regime_old_ref": regime,
        "regime_new_ref": regime,
        "objective_J_profile_ref": ref("omega/objective_J_profile.json"),
        "continuity_budget": {
            "schema_name": "budget_spec_v1",
            "schema_version": "v19_0",
            "max_steps": 1,
            "max_bytes_read": 0,
            "max_bytes_write": 0,
            "max_items": 1,
            "seed": 0,
            "policy": "SAFE_HALT",
        },
        "morphisms": [
            {
                "morphism_ref": {"artifact_id": morphism_id, "artifact_relpath": morphism_rel},
                "overlap_profile_ref": ref("omega/overlap.json"),
                "translator_bundle_ref": ref("omega/translator.json"),
                "totality_cert_ref": ref("omega/totality.json"),
                "continuity_receipt_ref": ref("omega/continuity.json"),
                "axis_specific_proof_refs": [ref("omega/proof.json")],
            }
        ],
    }
    axis_payload = dict(axis_without_id)
    axis_payload["axis_bundle_id"] = canon_hash_obj(axis_without_id)
    write_canon_json(axis_dir / "axis_upgrade_bundle_v1.json", axis_payload)

    module = _load_pipeline_module()
    report_ok, fatal_ok, nonfatal_ok = module._build_report(runs_root=runs_root)
    assert report_ok["proof_status"] == "PASS"
    assert fatal_ok == []
    assert nonfatal_ok == []

    dispatch_receipt_path = sorted(dispatch_dir.glob("sha256_*.omega_dispatch_receipt_v1.json"), key=lambda p: p.as_posix())[-1]
    raw = dispatch_receipt_path.read_bytes()
    # Single-byte modification that preserves valid + canonical JSON but invalidates the filename hash.
    if b"campaign_x" not in raw:
        raise AssertionError("expected dispatch receipt to contain campaign_x")
    raw_mut = raw.replace(b"campaign_x", b"campaign_y", 1)
    dispatch_receipt_path.write_bytes(raw_mut)

    report_bad, fatal_bad, _nonfatal_bad = module._build_report(runs_root=runs_root)
    assert report_bad["proof_status"] == "FAIL"
    fatal_codes = {row.get("code") for row in fatal_bad}
    assert "HASH_MISMATCH_FILENAME" in fatal_codes
