from __future__ import annotations

import pytest

from cdel.v18_0.omega_common_v1 import tree_hash
from cdel.v18_0.verify_rsi_omega_daemon_v1 import OmegaV18Error, _replay_promoted_subverifier


def test_replay_does_not_ignore_invalid_reason(tmp_path, monkeypatch) -> None:
    state_root = tmp_path / "state_root"
    subrun_state_dir = state_root / "subruns" / "tick_action" / "daemon" / "rsi_sas_system_v14_0" / "state"
    subrun_state_dir.mkdir(parents=True, exist_ok=True)
    (subrun_state_dir / "placeholder.txt").write_text("x", encoding="utf-8")
    replay_repo_root = state_root / "dispatch" / "tick_action" / "verifier" / "replay_repo_root"
    replay_repo_root.mkdir(parents=True, exist_ok=True)
    (replay_repo_root / "placeholder.txt").write_text("snapshot", encoding="utf-8")

    dispatch_payload = {
        "subrun": {
            "subrun_root_rel": "subruns/tick_action",
            "state_dir_rel": "daemon/rsi_sas_system_v14_0/state",
        }
    }
    subverifier_payload = {
        "verifier_module": "cdel.v14_0.verify_rsi_sas_system_v1",
        "state_dir_hash": tree_hash(subrun_state_dir),
        "replay_repo_root_rel": "dispatch/tick_action/verifier/replay_repo_root",
        "replay_repo_root_hash": tree_hash(replay_repo_root),
    }

    def _fake_run(*, state_root, verifier_module, state_arg, replay_state_dir, replay_repo_root):  # type: ignore[no-untyped-def]
        return 1, "INVALID:IMMUTABLE_TREE_MODIFIED", "INVALID:IMMUTABLE_TREE_MODIFIED"

    monkeypatch.setattr("cdel.v18_0.verify_rsi_omega_daemon_v1._run_subverifier_replay_cmd", _fake_run)

    with pytest.raises(OmegaV18Error, match="SUBVERIFIER_REPLAY_FAIL"):
        _replay_promoted_subverifier(
            state_root=state_root,
            dispatch_payload=dispatch_payload,
            subverifier_payload=subverifier_payload,
        )


def test_replay_requires_v14_snapshot_binding(tmp_path) -> None:
    state_root = tmp_path / "state_root"
    subrun_state_dir = state_root / "subruns" / "tick_action" / "daemon" / "rsi_sas_system_v14_0" / "state"
    subrun_state_dir.mkdir(parents=True, exist_ok=True)
    (subrun_state_dir / "placeholder.txt").write_text("x", encoding="utf-8")

    dispatch_payload = {
        "subrun": {
            "subrun_root_rel": "subruns/tick_action",
            "state_dir_rel": "daemon/rsi_sas_system_v14_0/state",
        }
    }
    subverifier_payload = {
        "verifier_module": "cdel.v14_0.verify_rsi_sas_system_v1",
        "state_dir_hash": tree_hash(subrun_state_dir),
        "replay_repo_root_rel": None,
        "replay_repo_root_hash": None,
    }

    with pytest.raises(OmegaV18Error, match="SUBVERIFIER_REPLAY_FAIL"):
        _replay_promoted_subverifier(
            state_root=state_root,
            dispatch_payload=dispatch_payload,
            subverifier_payload=subverifier_payload,
        )
