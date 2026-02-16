from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def csi_run_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    repo_root = Path(__file__).resolve().parents[4]
    pack = repo_root / "campaigns" / "rsi_real_csi_v2_2" / "rsi_real_csi_pack_v1.json"
    out_dir = tmp_path_factory.mktemp("csi_run") / "run"

    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "Extension-1" / "agi-orchestrator")

    cmd = [
        sys.executable,
        "-m",
        "orchestrator.rsi_csi_v2_2",
        "--csi_pack",
        str(pack),
        "--out_dir",
        str(out_dir),
    ]
    result = subprocess.run(cmd, env=env, check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout
    assert result.stdout.strip() == "VALID"
    return out_dir
