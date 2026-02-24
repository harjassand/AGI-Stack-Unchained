from __future__ import annotations

from pathlib import Path

from cdel.v18_0.omega_common_v1 import canon_hash_obj
from cdel.v19_0 import omega_promoter_v1 as promoter_v19
from cdel.v1_7r.canon import write_canon_json


def _write_hashed_json(out_dir: Path, suffix: str, payload: dict[str, object]) -> tuple[Path, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    digest = canon_hash_obj(payload)
    path = out_dir / f"sha256_{digest.split(':', 1)[1]}.{suffix}"
    write_canon_json(path, payload)
    return path, digest


def _make_dispatch_ctx(tmp_path: Path) -> tuple[dict[str, object], Path]:
    run_root = tmp_path / "runs" / "arena_budget_tick_0001"
    state_root = run_root / "daemon" / "rsi_omega_daemon_v19_0" / "state"
    dispatch_dir = state_root / "dispatch" / "d01"
    subrun_root = state_root / "subruns" / "d01_rsi_proposer_arena_v1"
    (subrun_root / "state" / "arena").mkdir(parents=True, exist_ok=True)
    (subrun_root / "promotion").mkdir(parents=True, exist_ok=True)
    ctx = {
        "dispatch_dir": dispatch_dir,
        "state_root": state_root,
        "subrun_root_abs": subrun_root,
        "campaign_entry": {
            "campaign_id": "rsi_proposer_arena_v1",
            "capability_id": "RSI_PROPOSER_ARENA_V1",
            "promotion_bundle_rel": "promotion/sha256_*.omega_promotion_bundle_ccap_v1.json",
            "campaign_pack_rel": "campaigns/rsi_proposer_arena_v1/rsi_proposer_arena_pack_v1.json",
            "state_dir_rel": "state",
        },
    }
    return ctx, subrun_root


def _write_arena_receipts(arena_dir: Path, winner_candidate_id: str) -> None:
    other_a = "sha256:" + ("2" * 64)
    other_b = "sha256:" + ("3" * 64)
    considered = [
        {"candidate_id": winner_candidate_id, "score_q32": 100, "cost_q32": 5, "risk_class": "LOW"},
        {"candidate_id": other_a, "score_q32": 90, "cost_q32": 5, "risk_class": "LOW"},
        {"candidate_id": other_b, "score_q32": 80, "cost_q32": 5, "risk_class": "LOW"},
    ]
    selection_payload = {
        "schema_version": "arena_selection_receipt_v1",
        "receipt_id": "sha256:" + ("0" * 64),
        "inputs_descriptor_id": "sha256:" + ("1" * 64),
        "arena_state_in_id": "sha256:" + ("2" * 64),
        "candidates_considered": considered,
        "ranked_candidate_ids": [winner_candidate_id, other_a, other_b],
        "winner_candidate_id": winner_candidate_id,
        "tie_break_proof": {
            "seed": "sha256:" + ("4" * 64),
            "ordered_candidate_ids": [winner_candidate_id, other_a, other_b],
            "chosen_candidate_id": winner_candidate_id,
        },
        "selection_reason_codes": ["ARENA_SELECT:WINNER_FROM_BACKLOG"],
    }
    run_payload = {
        "schema_version": "proposer_arena_run_receipt_v1",
        "receipt_id": "sha256:" + ("0" * 64),
        "tick_u64": 1,
        "arena_state_out_id": "sha256:" + ("5" * 64),
        "n_generated_u64": 16,
        "n_admitted_u64": 8,
        "n_backlogged_u64": 2,
        "n_considered_u64": 3,
        "winner_kind": "PATCH",
        "winner_candidate_id": winner_candidate_id,
        "winner_agent_id": "sh1_v0_3",
        "drop_reason_histogram": {},
        "notes": "",
    }
    _write_hashed_json(arena_dir, "arena_selection_receipt_v1.json", selection_payload)
    _write_hashed_json(arena_dir, "proposer_arena_run_receipt_v1.json", run_payload)


def _write_min_bundle(subrun_root: Path, winner_candidate_id: str) -> tuple[Path, str]:
    payload = {
        "schema_version": "omega_promotion_bundle_ccap_v1",
        "ccap_id": "sha256:" + ("6" * 64),
        "ccap_relpath": "ccap/placeholder.ccap_v1.json",
        "patch_relpath": "patches/placeholder.patch",
        "touched_paths": [],
        "activation_key": winner_candidate_id,
    }
    return _write_hashed_json((subrun_root / "promotion").resolve(), "omega_promotion_bundle_ccap_v1.json", payload)


def _valid_subverifier_receipt() -> dict[str, object]:
    return {
        "schema_version": "omega_subverifier_receipt_v1",
        "receipt_id": "sha256:" + ("7" * 64),
        "tick_u64": 1,
        "campaign_id": "rsi_proposer_arena_v1",
        "verifier_module": "cdel.v19_0.verify_rsi_proposer_arena_v1",
        "verifier_mode": "full",
        "state_dir_hash": "sha256:" + ("8" * 64),
        "result": {"status": "VALID", "reason_code": None},
        "stdout_hash": "sha256:" + ("9" * 64),
        "stderr_hash": "sha256:" + ("a" * 64),
    }


def test_budget_no_k_times_official_eval_v1(tmp_path: Path, monkeypatch) -> None:
    dispatch_ctx, subrun_root = _make_dispatch_ctx(tmp_path)
    winner_candidate_id = "sha256:" + ("1" * 64)
    _write_arena_receipts((subrun_root / "state" / "arena").resolve(), winner_candidate_id)
    bundle_path, bundle_hash = _write_min_bundle(subrun_root, winner_candidate_id)

    monkeypatch.setattr(promoter_v19.v18_promoter, "_find_promotion_bundle", lambda _ctx: (bundle_path, bundle_hash))
    monkeypatch.setattr(promoter_v19, "_load_arena_pack_and_assert_single_winner", lambda _ctx: None)
    monkeypatch.setattr(
        promoter_v19,
        "_axis_gate_context_for_bundle",
        lambda **_: (
            {
                "axis_gate_required_b": False,
                "axis_gate_exempted_b": False,
                "axis_gate_reason_code": "NONE",
                "axis_gate_axis_id": None,
                "axis_gate_bundle_present_b": False,
                "axis_gate_bundle_sha256": None,
                "axis_gate_checked_relpaths_v1": [],
            },
            None,
            {},
        ),
    )
    monkeypatch.setattr(promoter_v19, "_verify_axis_bundle_gate", lambda **_: {"axis_gate_required_b": False})
    monkeypatch.setattr(promoter_v19, "_baseline_ref_hash", lambda *_, **__: "sha256:" + ("0" * 64))
    monkeypatch.setattr(promoter_v19, "_nontrivial_delta_for_bundle", lambda **_: 0)
    monkeypatch.setattr(promoter_v19, "_load_latest_runtime_stats", lambda _ctx: (None, None))
    monkeypatch.setattr(promoter_v19, "_write_utility_proof_receipt", lambda **_: ({}, "sha256:" + ("b" * 64)))

    calls = {"v18_run_promotion": 0}

    def _fake_v18_run_promotion(**_: object) -> tuple[dict[str, object], str]:
        calls["v18_run_promotion"] += 1
        return (
            {
                "schema_version": "omega_promotion_receipt_v1",
                "receipt_id": "sha256:" + ("c" * 64),
                "tick_u64": 1,
                "promotion_bundle_hash": bundle_hash,
                "execution_mode": "STRICT",
                "meta_core_verifier_fingerprint": {
                    "constitution_meta_hash": "sha256:" + ("d" * 64),
                    "binary_hash_or_build_id": "sha256:" + ("e" * 64),
                },
                "result": {"status": "REJECTED", "reason_code": "CCAP_RECEIPT_REJECTED", "route": "NONE"},
                "active_manifest_hash_after": None,
            },
            "sha256:" + ("f" * 64),
        )

    monkeypatch.setattr(promoter_v19.v18_promoter, "run_promotion", _fake_v18_run_promotion)

    receipt, _digest = promoter_v19.run_promotion(
        tick_u64=1,
        dispatch_ctx=dispatch_ctx,
        subverifier_receipt=_valid_subverifier_receipt(),
        allowlists={},
    )

    assert calls["v18_run_promotion"] == 1
    assert receipt is not None
    assert str((receipt.get("result") or {}).get("reason_code", "")).startswith("ARENA_REJECT:CCAP_REJECTED:")
