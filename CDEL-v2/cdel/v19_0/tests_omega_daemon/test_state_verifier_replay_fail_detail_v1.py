from __future__ import annotations

import json
from pathlib import Path

from cdel.v19_0 import verify_rsi_omega_daemon_v1 as verifier


def test_write_state_verifier_replay_fail_detail_emits_hashed_sidecar(tmp_path: Path, monkeypatch) -> None:
    run_root = tmp_path / "run"
    state_dir = run_root / "state"
    config_dir = run_root / "config"
    state_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        verifier.verify_v18_module,
        "get_last_subverifier_replay_fail_detail",
        lambda: {
            "tick_u64": 17,
            "campaign_id": "rsi_ge_symbiotic_optimizer_sh1_v0_1",
            "verifier_module": "cdel.v18_0.verify_ccap_v1",
            "subrun_state_dir_rel": "subruns/tick_action/state",
            "expected_state_dir_hash": "sha256:" + ("1" * 64),
            "recomputed_state_dir_hash": "sha256:" + ("2" * 64),
            "reason_branch": "REPLAY_CMD_FAILED",
            "reason_detail": "REPLAY_VERIFIER_FAILED:INVALID:SCHEMA_FAIL",
            "replay_cmd_exit_code": 1,
            "replay_cmd_args_v1": [
                "/usr/bin/python3",
                "-m",
                "cdel.v18_0.verify_ccap_v1",
                "--mode",
                "full",
            ],
            "replay_cmd_stdout_tail_v1": ["INVALID:SCHEMA_FAIL"],
            "replay_cmd_stderr_tail_v1": ["traceback line"],
        },
    )

    detail_hash = verifier._write_state_verifier_replay_fail_detail(
        state_dir=state_dir,
        exc=RuntimeError("INVALID:SUBVERIFIER_REPLAY_FAIL"),
    )
    assert isinstance(detail_hash, str)
    assert detail_hash.startswith("sha256:")
    detail_path = run_root / "state_verifier" / f"sha256_{detail_hash.split(':', 1)[1]}.state_verifier_subverifier_replay_fail_detail_v1.json"
    assert detail_path.exists() and detail_path.is_file()
    payload = json.loads(detail_path.read_text(encoding="utf-8"))
    assert payload["reason_branch"] == "REPLAY_CMD_FAILED"
    assert payload["tick_u64"] == 17
    assert payload["campaign_id"] == "rsi_ge_symbiotic_optimizer_sh1_v0_1"
    assert payload["replay_cmd_exit_code"] == 1
