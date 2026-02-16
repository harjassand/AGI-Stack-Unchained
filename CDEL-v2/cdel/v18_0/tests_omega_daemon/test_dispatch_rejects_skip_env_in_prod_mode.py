from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from cdel.v18_0.omega_common_v1 import OmegaV18Error
from cdel.v18_0.omega_executor_v1 import dispatch_campaign


def test_dispatch_rejects_skip_env_in_prod_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    run_called = {"value": False}

    def _fake_run_module(*, py_module: str, argv: list[str], cwd: Path, output_dir: Path, extra_env: dict[str, str] | None = None) -> dict[str, Any]:
        run_called["value"] = True
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "stdout.log").write_text("ok\n", encoding="utf-8")
        (output_dir / "stderr.log").write_text("", encoding="utf-8")
        out_idx = argv.index("--out_dir") + 1
        out_abs = (cwd / argv[out_idx]).resolve()
        (out_abs / "daemon" / "rsi_sas_code_v12_0" / "state").mkdir(parents=True, exist_ok=True)
        return {
            "return_code": 0,
            "stdout_hash": "sha256:" + ("0" * 64),
            "stderr_hash": "sha256:" + ("0" * 64),
            "env_fingerprint_hash": "sha256:" + ("1" * 64),
        }

    monkeypatch.setattr("cdel.v18_0.omega_executor_v1.run_module", _fake_run_module)
    monkeypatch.setenv("V16_1_SKIP_DETERMINISM", "1")
    monkeypatch.delenv("OMEGA_DEV_BENCHMARK_MODE", raising=False)

    decision_plan = {
        "action_kind": "RUN_CAMPAIGN",
        "campaign_id": "rsi_sas_code_v12_0",
        "plan_id": "sha256:" + ("a" * 64),
    }
    registry = {
        "capabilities": [
            {
                "campaign_id": "rsi_sas_code_v12_0",
                "capability_id": "RSI_SAS_CODE",
                "enabled": True,
                "campaign_pack_rel": "campaigns/rsi_sas_code_v12_0/rsi_sas_code_pack_v12_0.json",
                "state_dir_rel": "daemon/rsi_sas_code_v12_0/state",
                "orchestrator_module": "orchestrator.rsi_sas_code_v12_0",
                "verifier_module": "cdel.v12_0.verify_rsi_sas_code_v1",
                "cooldown_ticks_u64": 0,
                "budget_cost_hint_q32": {"q": 0},
            }
        ]
    }

    with pytest.raises(OmegaV18Error, match="FORBIDDEN_SKIP_ENV"):
        dispatch_campaign(
            tick_u64=1,
            decision_plan=decision_plan,
            registry=registry,
            state_root=state_root,
            run_seed_u64=123,
            runaway_cfg=None,
        )

    assert run_called["value"] is False


def test_dispatch_allows_skip_env_in_dev_benchmark_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    run_called = {"value": False}

    def _fake_run_module(*, py_module: str, argv: list[str], cwd: Path, output_dir: Path, extra_env: dict[str, str] | None = None) -> dict[str, Any]:
        run_called["value"] = True
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "stdout.log").write_text("ok\n", encoding="utf-8")
        (output_dir / "stderr.log").write_text("", encoding="utf-8")
        out_idx = argv.index("--out_dir") + 1
        out_abs = (cwd / argv[out_idx]).resolve()
        (out_abs / "daemon" / "rsi_sas_code_v12_0" / "state").mkdir(parents=True, exist_ok=True)
        return {
            "return_code": 0,
            "stdout_hash": "sha256:" + ("0" * 64),
            "stderr_hash": "sha256:" + ("0" * 64),
            "env_fingerprint_hash": "sha256:" + ("1" * 64),
        }

    monkeypatch.setattr("cdel.v18_0.omega_executor_v1.run_module", _fake_run_module)
    monkeypatch.setenv("V16_1_SKIP_DETERMINISM", "1")
    monkeypatch.setenv("OMEGA_DEV_BENCHMARK_MODE", "1")

    decision_plan = {
        "action_kind": "RUN_CAMPAIGN",
        "campaign_id": "rsi_sas_code_v12_0",
        "plan_id": "sha256:" + ("a" * 64),
    }
    registry = {
        "capabilities": [
            {
                "campaign_id": "rsi_sas_code_v12_0",
                "capability_id": "RSI_SAS_CODE",
                "enabled": True,
                "campaign_pack_rel": "campaigns/rsi_sas_code_v12_0/rsi_sas_code_pack_v12_0.json",
                "state_dir_rel": "daemon/rsi_sas_code_v12_0/state",
                "orchestrator_module": "orchestrator.rsi_sas_code_v12_0",
                "verifier_module": "cdel.v12_0.verify_rsi_sas_code_v1",
                "cooldown_ticks_u64": 0,
                "budget_cost_hint_q32": {"q": 0},
            }
        ]
    }

    receipt, _digest, _ctx = dispatch_campaign(
        tick_u64=1,
        decision_plan=decision_plan,
        registry=registry,
        state_root=state_root,
        run_seed_u64=123,
        runaway_cfg=None,
    )

    assert receipt is not None
    assert run_called["value"] is True
