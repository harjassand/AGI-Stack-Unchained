from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from cdel.v18_0.omega_common_v1 import repo_root
from cdel.v18_0.omega_executor_v1 import dispatch_campaign


def test_dispatch_v12_uses_canonical_workspace_invocation(tmp_path, monkeypatch) -> None:
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    captured: dict[str, Any] = {}

    def _fake_run_module(*, py_module: str, argv: list[str], cwd: Path, output_dir: Path, extra_env: dict[str, str] | None = None) -> dict[str, Any]:
        captured["py_module"] = py_module
        captured["argv"] = list(argv)
        captured["cwd"] = cwd
        captured["output_dir"] = output_dir
        out_index = argv.index("--out_dir") + 1
        out_rel = Path(argv[out_index])
        out_abs = (cwd / out_rel).resolve()
        (out_abs / "daemon" / "rsi_sas_code_v12_0" / "state").mkdir(parents=True, exist_ok=True)
        (out_abs / "marker.txt").write_text("ok\n", encoding="utf-8")
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "stdout.log").write_text("ok\n", encoding="utf-8")
        (output_dir / "stderr.log").write_text("", encoding="utf-8")
        return {
            "return_code": 0,
            "stdout_hash": "sha256:" + ("0" * 64),
            "stderr_hash": "sha256:" + ("0" * 64),
            "env_fingerprint_hash": "sha256:" + ("1" * 64),
        }

    monkeypatch.setattr("cdel.v18_0.omega_executor_v1.run_module", _fake_run_module)

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

    receipt, _digest, ctx = dispatch_campaign(
        tick_u64=1,
        decision_plan=decision_plan,
        registry=registry,
        state_root=state_root,
        run_seed_u64=123,
        runaway_cfg=None,
    )

    assert receipt is not None
    assert ctx is not None
    assert captured["cwd"] == repo_root()
    assert captured["argv"][0:2] == [
        "--campaign_pack",
        "campaigns/rsi_sas_code_v12_0/rsi_sas_code_pack_v12_0.json",
    ]
    out_index = captured["argv"].index("--out_dir") + 1
    out_dir_rel = captured["argv"][out_index]
    assert out_dir_rel.startswith(".omega_v18_exec_workspace/")
    assert (ctx["subrun_root_abs"] / "marker.txt").exists()
