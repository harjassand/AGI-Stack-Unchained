from __future__ import annotations

from cdel.v18_0.omega_common_v1 import tree_hash
from cdel.v18_0.verify_rsi_omega_daemon_v1 import _replay_promoted_subverifier


def test_replay_uses_smg_state_dir_for_model_genesis(tmp_path, monkeypatch) -> None:
    state_root = tmp_path / "state_root"
    subrun_state_dir = state_root / "subruns" / "tick_action" / "daemon" / "rsi_model_genesis_v10_0" / "state"
    subrun_state_dir.mkdir(parents=True, exist_ok=True)
    (subrun_state_dir / "placeholder.txt").write_text("x", encoding="utf-8")

    dispatch_payload = {
        "subrun": {
            "subrun_root_rel": "subruns/tick_action",
            "state_dir_rel": "daemon/rsi_model_genesis_v10_0/state",
        },
        "invocation": {
            "env_overrides": {},
        },
    }
    subverifier_payload = {
        "verifier_module": "cdel.v10_0.verify_rsi_model_genesis_v1",
        "state_dir_hash": tree_hash(subrun_state_dir),
        "replay_repo_root_rel": None,
        "replay_repo_root_hash": None,
    }

    captured: dict[str, str] = {}

    def _fake_run(**kwargs):  # type: ignore[no-untyped-def]
        captured["state_arg"] = str(kwargs.get("state_arg", ""))
        return 0, "VALID", "VALID"

    monkeypatch.setattr("cdel.v18_0.verify_rsi_omega_daemon_v1._run_subverifier_replay_cmd", _fake_run)

    _replay_promoted_subverifier(
        state_root=state_root,
        dispatch_payload=dispatch_payload,
        subverifier_payload=subverifier_payload,
    )
    assert captured["state_arg"] == "--smg_state_dir"
