from __future__ import annotations

from pathlib import Path

from cdel.v19_0 import omega_promoter_v1 as promoter


def _base_subverifier_receipt() -> dict[str, object]:
    return {
        "schema_version": "omega_subverifier_receipt_v1",
        "receipt_id": "sha256:" + ("0" * 64),
        "tick_u64": 1,
        "campaign_id": "rsi_ge_symbiotic_optimizer_sh1_v0_1",
        "verifier_module": "cdel.v18_0.verify_ccap_v1",
        "verifier_mode": "full",
        "state_dir_hash": "sha256:" + ("1" * 64),
        "replay_repo_root_rel": None,
        "replay_repo_root_hash": None,
        "result": {"status": "VALID", "reason_code": None},
        "stdout_hash": "sha256:" + ("2" * 64),
        "stderr_hash": "sha256:" + ("3" * 64),
    }


def _base_nontriviality_cert() -> dict[str, object]:
    return {
        "schema_name": "nontriviality_cert_v1",
        "schema_version": "v1",
        "policy_id": "nontriviality_policy_v2",
        "threshold_profile_id": "nontriviality_policy_v2_thresholds_v1",
        "thresholds_v1": {"wiring_ast_nodes_min_u32": 12},
        "patch_parse_ok_b": True,
        "ast_parse_ok_b": True,
        "touched_paths_u32": 1,
        "touched_relpaths_v1": ["orchestrator/omega_v18_0/goal_synthesizer_v1.py"],
        "ast_nodes_changed_u32": 14,
        "control_flow_changed_b": True,
        "call_edges_changed_b": True,
        "data_flow_changed_b": False,
        "public_api_changed_b": False,
        "lines_added_u32": 8,
        "lines_deleted_u32": 1,
        "wiring_class_ok_b": True,
        "archetype_id": None,
        "archetype_pass_b": None,
        "shape_id": "sha256:" + ("4" * 64),
        "failed_threshold_code": None,
    }


def test_subverifier_rewrite_drops_invalid_nontriviality_cert(tmp_path: Path) -> None:
    dispatch_dir = tmp_path / "dispatch" / "abc123"
    cert = _base_nontriviality_cert()
    cert["patch_parse_ok_b"] = False
    cert["touched_paths_u32"] = 0
    cert["touched_relpaths_v1"] = []
    cert["ast_nodes_changed_u32"] = 0
    cert["control_flow_changed_b"] = False
    cert["call_edges_changed_b"] = False
    cert["wiring_class_ok_b"] = False
    cert["failed_threshold_code"] = "PATCH_PARSE_FAILED"

    rewritten, _digest = promoter._rewrite_subverifier_receipt(
        dispatch_ctx={"dispatch_dir": str(dispatch_dir)},
        receipt=_base_subverifier_receipt(),
        status="INVALID",
        reason_code="VERIFY_ERROR:INSUFFICIENT_NONTRIVIAL_DELTA",
        nontriviality_cert_v1=cert,
    )

    assert rewritten["result"]["status"] == "INVALID"
    assert rewritten["result"]["reason_code"] == "VERIFY_ERROR:INSUFFICIENT_NONTRIVIAL_DELTA"
    assert rewritten["nontriviality_cert_v1"] is None


def test_subverifier_rewrite_keeps_valid_nontriviality_cert(tmp_path: Path) -> None:
    dispatch_dir = tmp_path / "dispatch" / "def456"
    cert = _base_nontriviality_cert()

    rewritten, _digest = promoter._rewrite_subverifier_receipt(
        dispatch_ctx={"dispatch_dir": str(dispatch_dir)},
        receipt=_base_subverifier_receipt(),
        status="VALID",
        reason_code=None,
        nontriviality_cert_v1=cert,
    )

    cert_out = rewritten["nontriviality_cert_v1"]
    assert isinstance(cert_out, dict)
    assert cert_out["wiring_class_ok_b"] is True
    assert cert_out["touched_relpaths_v1"] == ["orchestrator/omega_v18_0/goal_synthesizer_v1.py"]
