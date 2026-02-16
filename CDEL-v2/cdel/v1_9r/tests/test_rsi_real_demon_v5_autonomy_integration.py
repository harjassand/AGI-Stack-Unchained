from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def test_rsi_real_demon_v5_autonomy_integration() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    pack_path = repo_root / "campaigns" / "rsi_real_demon_v5_autonomy" / "rsi_real_demon_campaign_pack_v5.json"
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "rsi_real_demon_v5_autonomy"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(repo_root / "Extension-1" / "agi-orchestrator")
        cmd = [
            sys.executable,
            "-m",
            "orchestrator.rsi_autonomy_v1",
            "--campaign_pack",
            str(pack_path),
            "--out_dir",
            str(out_dir),
        ]
        result = subprocess.run(cmd, env=env, check=False, capture_output=True, text=True)
        assert result.returncode == 0
        assert result.stdout.strip() == "VALID"
