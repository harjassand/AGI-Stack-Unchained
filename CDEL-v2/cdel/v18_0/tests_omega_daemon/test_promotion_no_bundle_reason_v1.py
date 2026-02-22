from __future__ import annotations

from pathlib import Path

from cdel.v18_0.omega_allowlists_v1 import load_allowlists
from cdel.v18_0.omega_promoter_v1 import run_promotion
from cdel.v1_7r.canon import write_canon_json


def _allowlists() -> dict:
    path = Path(__file__).resolve().parents[4] / "campaigns" / "rsi_omega_daemon_v18_0" / "omega_allowlists_v1.json"
    return load_allowlists(path)[0]


def _dispatch_ctx(tmp_path: Path) -> dict[str, object]:
    run_root = tmp_path / "runs" / "mutator_no_bundle_tick_0001"
    state_root = run_root / "daemon" / "rsi_omega_daemon_v18_0" / "state"
    dispatch_dir = state_root / "dispatch" / "a01"
    subrun_root = state_root / "subruns" / "a01_rsi_coordinator_mutator_v1"
    dispatch_dir.mkdir(parents=True, exist_ok=True)
    subrun_root.mkdir(parents=True, exist_ok=True)
    return {
        "dispatch_dir": dispatch_dir,
        "state_root": state_root,
        "subrun_root_abs": subrun_root,
        "campaign_entry": {
            "campaign_id": "rsi_coordinator_mutator_v1",
            "capability_id": "RSI_COORDINATOR_MUTATOR",
            "promotion_bundle_rel": "promotion/sha256_*.omega_promotion_bundle_ccap_v1.json",
        },
    }


def _valid_subverifier() -> dict[str, object]:
    return {"result": {"status": "VALID", "reason_code": None}}


def test_no_bundle_maps_micro_bench_gate_failure_reason(tmp_path: Path) -> None:
    dispatch_ctx = _dispatch_ctx(tmp_path)
    write_canon_json(
        Path(dispatch_ctx["dispatch_dir"]) / "coordinator_mutator_verify_failure_v1.json",
        {
            "schema_version": "coordinator_mutator_verify_failure_v1",
            "tick_u64": 1,
            "reason": "MICRO_BENCH_GATE_FAIL",
        },
    )
    receipt, _ = run_promotion(
        tick_u64=1,
        dispatch_ctx=dispatch_ctx,
        subverifier_receipt=_valid_subverifier(),
        allowlists=_allowlists(),
    )
    assert receipt is not None
    assert receipt["result"]["status"] == "SKIPPED"
    assert receipt["result"]["reason_code"] == "NO_BUNDLE_MICRO_BENCH_GATE_FAIL"


def test_no_bundle_maps_replay_failure_reason(tmp_path: Path) -> None:
    dispatch_ctx = _dispatch_ctx(tmp_path)
    write_canon_json(
        Path(dispatch_ctx["dispatch_dir"]) / "coordinator_mutator_replay_failure_v1.json",
        {
            "schema_version": "coordinator_mutator_replay_failure_v1",
            "tick_u64": 1,
            "detail": "INVALID",
        },
    )
    receipt, _ = run_promotion(
        tick_u64=1,
        dispatch_ctx=dispatch_ctx,
        subverifier_receipt=_valid_subverifier(),
        allowlists=_allowlists(),
    )
    assert receipt is not None
    assert receipt["result"]["status"] == "SKIPPED"
    assert receipt["result"]["reason_code"] == "NO_BUNDLE_REPLAY_INVALID"
