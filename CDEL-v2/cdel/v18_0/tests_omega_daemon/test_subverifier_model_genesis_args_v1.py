from __future__ import annotations

from pathlib import Path

from cdel.v18_0.omega_promoter_v1 import run_subverifier


def test_model_genesis_subverifier_uses_smg_state_dir_flag(tmp_path: Path, monkeypatch) -> None:
    state_root = tmp_path / "state"
    dispatch_dir = state_root / "dispatch" / "a01"
    subrun_state = state_root / "subruns" / "a01_mg" / "daemon" / "rsi_model_genesis_v10_0" / "state"

    dispatch_dir.mkdir(parents=True, exist_ok=True)
    subrun_state.mkdir(parents=True, exist_ok=True)
    (subrun_state / "placeholder.txt").write_text("ok", encoding="utf-8")

    captured: dict[str, object] = {}

    def _fake_run_module(*, py_module: str, argv: list[str], cwd: Path, output_dir: Path, extra_env=None):
        captured["py_module"] = py_module
        captured["argv"] = list(argv)
        output_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = output_dir / "stdout.log"
        stderr_path = output_dir / "stderr.log"
        stdout_path.write_text("VALID\n", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        return {
            "return_code": 0,
            "stdout_path": stdout_path,
            "stderr_path": stderr_path,
            "stdout_hash": "sha256:" + ("1" * 64),
            "stderr_hash": "sha256:" + ("0" * 64),
            "env_fingerprint_hash": "sha256:" + ("2" * 64),
        }

    monkeypatch.setattr("cdel.v18_0.omega_promoter_v1.run_module", _fake_run_module)

    dispatch_ctx = {
        "dispatch_dir": dispatch_dir,
        "state_root": state_root,
        "subrun_state_rel_state": "subruns/a01_mg/daemon/rsi_model_genesis_v10_0/state",
        "subrun_root_rel_state": "subruns/a01_mg",
        "campaign_entry": {
            "campaign_id": "rsi_model_genesis_v10_0",
            "verifier_module": "cdel.v10_0.verify_rsi_model_genesis_v1",
        },
        "invocation_env_overrides": {},
        "pythonpath": "",
    }

    receipt, _ = run_subverifier(tick_u64=1, dispatch_ctx=dispatch_ctx)

    assert receipt is not None
    assert receipt["result"]["status"] == "VALID"
    assert captured["py_module"] == "cdel.v10_0.verify_rsi_model_genesis_v1"
    argv = list(captured["argv"])  # type: ignore[arg-type]
    assert "--smg_state_dir" in argv
    assert "--state_dir" not in argv
    assert argv[argv.index("--smg_state_dir") + 1] == "subruns/a01_mg/daemon/rsi_model_genesis_v10_0/state"
