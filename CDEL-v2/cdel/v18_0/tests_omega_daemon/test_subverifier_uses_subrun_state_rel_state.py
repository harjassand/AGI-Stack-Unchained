from __future__ import annotations

from pathlib import Path
from typing import Any

from cdel.v18_0.omega_promoter_v1 import run_subverifier


def test_subverifier_uses_subrun_state_rel_state_without_exec_alias(tmp_path, monkeypatch) -> None:
    state_root = tmp_path / "state"
    dispatch_dir = state_root / "dispatch" / "a01"
    subrun_state_rel = "subruns/a01_rsi_sas_code_v12_0/daemon/rsi_sas_code_v12_0/state"
    subrun_state_abs = state_root / subrun_state_rel
    subrun_state_abs.mkdir(parents=True, exist_ok=True)
    (subrun_state_abs / "marker.txt").write_text("ok\n", encoding="utf-8")

    captured: dict[str, Any] = {}

    def _fake_run_module(*, py_module: str, argv: list[str], cwd: Path, output_dir: Path, extra_env: dict[str, str] | None = None) -> dict[str, Any]:
        captured["py_module"] = py_module
        captured["argv"] = list(argv)
        captured["cwd"] = cwd
        captured["extra_env"] = dict(extra_env or {})
        output_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = output_dir / "stdout.txt"
        stderr_path = output_dir / "stderr.txt"
        stdout_path.write_text("VALID\n", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        return {
            "return_code": 0,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "stdout_hash": "sha256:" + ("0" * 64),
            "stderr_hash": "sha256:" + ("0" * 64),
        }

    monkeypatch.setattr("cdel.v18_0.omega_promoter_v1.run_module", _fake_run_module)

    dispatch_ctx = {
        "campaign_entry": {
            "campaign_id": "rsi_sas_code_v12_0",
            "verifier_module": "cdel.v12_0.verify_rsi_sas_code_v1",
        },
        "state_root": state_root,
        "subrun_state_rel_state": subrun_state_rel,
        "dispatch_dir": dispatch_dir,
        "pythonpath": "",
        "invocation_env_overrides": {},
    }

    receipt, digest = run_subverifier(
        tick_u64=1,
        dispatch_ctx=dispatch_ctx,
    )

    assert digest is not None
    assert receipt is not None
    assert receipt["result"]["status"] == "VALID"
    assert captured["argv"] == ["--mode", "full", "--sas_code_state_dir", subrun_state_rel]
