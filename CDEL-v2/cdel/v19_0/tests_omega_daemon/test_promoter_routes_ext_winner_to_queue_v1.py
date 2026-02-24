from __future__ import annotations

from pathlib import Path

from cdel.v18_0 import omega_activator_v1 as activator_v18
from cdel.v18_0.omega_common_v1 import canon_hash_obj
from cdel.v19_0 import omega_promoter_v1 as promoter_v19
from cdel.v1_7r.canon import write_canon_json


def _write_hashed_json(out_dir: Path, suffix: str, payload: dict[str, object]) -> tuple[Path, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    digest = canon_hash_obj(payload)
    path = out_dir / f"sha256_{digest.split(':', 1)[1]}.{suffix}"
    write_canon_json(path, payload)
    return path, digest


def _write_plain_and_hashed(out_dir: Path, name: str, payload: dict[str, object]) -> str:
    out_dir.mkdir(parents=True, exist_ok=True)
    write_canon_json(out_dir / name, payload)
    digest = canon_hash_obj(payload)
    write_canon_json(out_dir / f"sha256_{digest.split(':', 1)[1]}.{name}", payload)
    return digest


def _make_dispatch_ctx(tmp_path: Path) -> tuple[dict[str, object], Path, Path]:
    run_root = tmp_path / "runs" / "arena_ext_route_tick_0001"
    state_root = run_root / "daemon" / "rsi_omega_daemon_v19_0" / "state"
    dispatch_dir = state_root / "dispatch" / "d01"
    subrun_root = state_root / "subruns" / "d01_rsi_proposer_arena_v1"
    (subrun_root / "state" / "arena").mkdir(parents=True, exist_ok=True)
    (subrun_root / "state" / "promotion").mkdir(parents=True, exist_ok=True)
    (dispatch_dir / "promotion").mkdir(parents=True, exist_ok=True)
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
    return ctx, dispatch_dir, subrun_root


def _write_arena_receipts(arena_dir: Path, *, winner_kind: str, winner_candidate_id: str, winner_agent_id: str) -> None:
    selection_payload = {
        "schema_version": "arena_selection_receipt_v1",
        "receipt_id": "sha256:" + ("0" * 64),
        "inputs_descriptor_id": "sha256:" + ("1" * 64),
        "arena_state_in_id": "sha256:" + ("2" * 64),
        "candidates_considered": [
            {
                "candidate_id": winner_candidate_id,
                "score_q32": 100,
                "cost_q32": 1,
                "risk_class": "LOW",
            }
        ],
        "ranked_candidate_ids": [winner_candidate_id],
        "winner_candidate_id": winner_candidate_id,
        "tie_break_proof": {
            "seed": "sha256:" + ("3" * 64),
            "ordered_candidate_ids": [winner_candidate_id],
            "chosen_candidate_id": winner_candidate_id,
        },
        "selection_reason_codes": ["ARENA_SELECT:WINNER_FROM_BACKLOG"],
    }
    run_payload = {
        "schema_version": "proposer_arena_run_receipt_v1",
        "receipt_id": "sha256:" + ("0" * 64),
        "tick_u64": 1,
        "arena_state_out_id": "sha256:" + ("4" * 64),
        "n_generated_u64": 1,
        "n_admitted_u64": 1,
        "n_backlogged_u64": 0,
        "n_considered_u64": 1,
        "winner_kind": winner_kind,
        "winner_candidate_id": winner_candidate_id,
        "winner_agent_id": winner_agent_id,
        "drop_reason_histogram": {},
        "notes": "",
    }
    _write_hashed_json(arena_dir, "arena_selection_receipt_v1.json", selection_payload)
    _write_hashed_json(arena_dir, "proposer_arena_run_receipt_v1.json", run_payload)


def _valid_subverifier_receipt() -> dict[str, object]:
    return {
        "schema_version": "omega_subverifier_receipt_v1",
        "receipt_id": "sha256:" + ("6" * 64),
        "tick_u64": 1,
        "campaign_id": "rsi_proposer_arena_v1",
        "verifier_module": "cdel.v19_0.verify_rsi_proposer_arena_v1",
        "verifier_mode": "full",
        "state_dir_hash": "sha256:" + ("7" * 64),
        "result": {"status": "VALID", "reason_code": None},
        "stdout_hash": "sha256:" + ("8" * 64),
        "stderr_hash": "sha256:" + ("9" * 64),
    }


def test_promoter_routes_ext_winner_to_queue_v1(tmp_path: Path, monkeypatch) -> None:
    dispatch_ctx, dispatch_dir, subrun_root = _make_dispatch_ctx(tmp_path)
    winner_candidate_id = "sha256:" + ("1" * 64)
    extension_id = "sha256:" + ("e" * 64)

    _write_arena_receipts(
        (subrun_root / "state" / "arena").resolve(),
        winner_kind="KERNEL_EXT_PROPOSAL",
        winner_candidate_id=winner_candidate_id,
        winner_agent_id="kernel_ext_mutator_v1",
    )

    ext_spec = {"schema_version": "kernel_extension_spec_v1", "extension_spec_id": extension_id}
    suite_manifest = {"schema_version": "benchmark_suite_manifest_v1", "suite_id": "sha256:" + ("a" * 64)}
    suite_set = {"schema_version": "benchmark_suite_set_v1", "suite_set_id": "sha256:" + ("b" * 64)}
    for root in [(subrun_root / "state" / "promotion"), (dispatch_dir / "promotion")]:
        _write_plain_and_hashed(root, "kernel_extension_spec_v1.json", ext_spec)
        _write_plain_and_hashed(root, "benchmark_suite_manifest_v1.json", suite_manifest)
        _write_plain_and_hashed(root, "benchmark_suite_set_v1.json", suite_set)

    monkeypatch.setattr(
        promoter_v19,
        "verify_extension_proposal_dir",
        lambda promotion_dir: (extension_id, ext_spec, suite_manifest, suite_set),
    )
    monkeypatch.setattr(promoter_v19, "_load_arena_pack_and_assert_single_winner", lambda _ctx: None)

    promotion_receipt, _promotion_hash = promoter_v19.run_promotion(
        tick_u64=1,
        dispatch_ctx=dispatch_ctx,
        subverifier_receipt=_valid_subverifier_receipt(),
        allowlists={},
    )

    assert promotion_receipt is not None
    assert str((promotion_receipt.get("result") or {}).get("status", "")) == "PROMOTED"
    assert str(promotion_receipt.get("result_kind", "")) == "PROMOTED_EXT_QUEUED"
    assert str(promotion_receipt.get("promotion_bundle_hash", "")) == extension_id

    monkeypatch.setattr(
        activator_v18,
        "_run_meta_core_apply",
        lambda **_: (_ for _ in ()).throw(AssertionError("meta-core apply must not run for EXT_QUEUED")),
    )

    activation_receipt, _activation_hash, rollback_receipt, _rollback_hash, final_hash = activator_v18.run_activation(
        tick_u64=1,
        dispatch_ctx=dispatch_ctx,
        promotion_receipt=promotion_receipt,
        healthcheck_suitepack={"checks": []},
        healthcheck_suite_hash="sha256:" + ("c" * 64),
        active_manifest_hash_before="sha256:" + ("d" * 64),
    )

    assert rollback_receipt is None
    assert activation_receipt is not None
    assert str(activation_receipt.get("activation_kind", "")) == "ACTIVATION_KIND_EXT_QUEUED"
    assert bool(activation_receipt.get("activation_success", False)) is True
    assert str(activation_receipt.get("extension_queued_status_code", "")) == "ACT_EXT_QUEUED:OK"
    assert str(activation_receipt.get("before_active_manifest_hash", "")) == str(
        activation_receipt.get("after_active_manifest_hash", "")
    )
    assert str(final_hash) == str(activation_receipt.get("before_active_manifest_hash", ""))
    ext_receipt_hash = str(activation_receipt.get("extension_queued_receipt_hash", "")).strip()
    assert ext_receipt_hash.startswith("sha256:")
