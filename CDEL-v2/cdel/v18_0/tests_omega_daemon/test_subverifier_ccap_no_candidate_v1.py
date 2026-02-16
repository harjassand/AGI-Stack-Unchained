from __future__ import annotations

from pathlib import Path

from cdel.v18_0.omega_promoter_v1 import run_subverifier


def test_ccap_subverifier_marks_no_candidate_valid(tmp_path: Path, monkeypatch) -> None:
    state_root = tmp_path / "state"
    dispatch_dir = state_root / "dispatch" / "a01"
    subrun_root = state_root / "subruns" / "a01_ccap"
    subrun_state = subrun_root / "daemon" / "mock" / "state"

    dispatch_dir.mkdir(parents=True, exist_ok=True)
    subrun_state.mkdir(parents=True, exist_ok=True)

    def _fail_if_called(**_kwargs):
        raise AssertionError("run_module should not execute when no CCAP candidate exists")

    monkeypatch.setattr("cdel.v18_0.omega_promoter_v1.run_module", _fail_if_called)

    dispatch_ctx = {
        "dispatch_dir": dispatch_dir,
        "state_root": state_root,
        "subrun_root_abs": subrun_root,
        "subrun_state_rel_state": "subruns/a01_ccap/daemon/mock/state",
        "subrun_root_rel_state": "subruns/a01_ccap",
        "campaign_entry": {
            "campaign_id": "mock_ccap_campaign",
            "verifier_module": "cdel.v18_0.verify_ccap_v1",
            "enable_ccap": 1,
        },
        "invocation_env_overrides": {},
        "pythonpath": "",
    }

    receipt, _ = run_subverifier(tick_u64=1, dispatch_ctx=dispatch_ctx)

    assert receipt is not None
    assert receipt["result"]["status"] == "VALID"
    assert receipt["result"]["reason_code"] is None
    assert (dispatch_dir / "verifier" / "stdout.log").exists()
