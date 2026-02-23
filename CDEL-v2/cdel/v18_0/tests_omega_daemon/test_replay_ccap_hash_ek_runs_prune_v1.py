from __future__ import annotations

import shutil
from pathlib import Path

from cdel.v18_0.omega_promoter_v1 import _tree_hash_ccap_subrun_for_receipt
from cdel.v18_0.verify_rsi_omega_daemon_v1 import (
    _replay_promoted_subverifier,
    _tree_hash_ccap_subrun_for_replay,
)


def test_replay_ccap_hash_stable_when_ek_runs_pruned(tmp_path: Path, monkeypatch) -> None:
    state_root = tmp_path / "state_root"
    subrun_root = state_root / "subruns" / "tick_action"
    subrun_state = subrun_root / "state"
    subrun_state.mkdir(parents=True, exist_ok=True)
    (subrun_state / "placeholder.txt").write_text("state", encoding="utf-8")
    ccap_dir = subrun_root / "ccap"
    ccap_dir.mkdir(parents=True, exist_ok=True)
    (ccap_dir / f"sha256_{'a' * 64}.ccap_v1.json").write_text("{}", encoding="utf-8")
    promotion_dir = subrun_root / "promotion"
    promotion_dir.mkdir(parents=True, exist_ok=True)
    (promotion_dir / "marker.txt").write_text("promotion", encoding="utf-8")
    ek_runs_dir = ccap_dir / "ek_runs" / "attempt_0001"
    ek_runs_dir.mkdir(parents=True, exist_ok=True)
    (ek_runs_dir / "workspace.bin").write_bytes(b"x" * 64)

    receipt_hash = _tree_hash_ccap_subrun_for_receipt(subrun_root)
    assert _tree_hash_ccap_subrun_for_replay(subrun_root) == receipt_hash

    shutil.rmtree(ccap_dir / "ek_runs")
    assert _tree_hash_ccap_subrun_for_replay(subrun_root) == receipt_hash

    dispatch_payload = {
        "subrun": {
            "subrun_root_rel": "subruns/tick_action",
            "state_dir_rel": "state",
        },
        "invocation": {
            "env_overrides": {},
        },
    }
    subverifier_payload = {
        "tick_u64": 1,
        "campaign_id": "rsi_ge_symbiotic_optimizer_sh1_v0_1",
        "verifier_module": "cdel.v18_0.verify_ccap_v1",
        "state_dir_hash": receipt_hash,
        "replay_repo_root_rel": None,
        "replay_repo_root_hash": None,
    }

    def _fake_run(**_kwargs):  # type: ignore[no-untyped-def]
        return 0, "VALID", "VALID"

    monkeypatch.setattr("cdel.v18_0.verify_rsi_omega_daemon_v1._run_subverifier_replay_cmd", _fake_run)
    _replay_promoted_subverifier(
        state_root=state_root,
        dispatch_payload=dispatch_payload,
        subverifier_payload=subverifier_payload,
    )
