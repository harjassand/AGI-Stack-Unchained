from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "CDEL-v2") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "CDEL-v2"))

from cdel.v18_0.omega_common_v1 import load_canon_dict


def _run_preflight(*, summary_path: Path) -> dict:
    env = dict(os.environ)
    env["OMEGA_CCAP_ALLOW_DIRTY_TREE"] = "1"
    env["OMEGA_META_CORE_ACTIVATION_MODE"] = "simulate"
    env["OMEGA_V19_DETERMINISTIC_TIMING"] = "1"
    env["ORCH_LLM_BACKEND"] = "mlx"
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "preflight_long_run_v1.py"),
        "--campaign_pack",
        "campaigns/rsi_omega_daemon_v19_0_long_run_v1/rsi_omega_daemon_pack_v1.json",
        "--run_root",
        "runs/long_run_preflight_v1_test",
        "--summary_path",
        str(summary_path),
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    payload = load_canon_dict(summary_path)
    return dict(payload)


def test_preflight_summary_is_deterministic_v1(tmp_path: Path) -> None:
    summary_path_a = tmp_path / "LONG_RUN_PREFLIGHT_SUMMARY_a_v1.json"
    summary_path_b = tmp_path / "LONG_RUN_PREFLIGHT_SUMMARY_b_v1.json"

    payload_a = _run_preflight(summary_path=summary_path_a)
    payload_b = _run_preflight(summary_path=summary_path_b)

    assert payload_a["schema_id"] == "long_run_preflight_summary_v1"
    assert payload_b["schema_id"] == "long_run_preflight_summary_v1"
    assert payload_a["id"] == payload_b["id"]
    assert payload_a["schema_checks"]["missing_schemas"] == []
    assert payload_a["schema_checks"]["mirror_mismatches"] == []
    assert all(bool(value) for value in payload_a["governance_checks"].values())
    assert payload_a == payload_b
