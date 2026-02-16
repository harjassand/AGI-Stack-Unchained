from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from cdel.v1_7r.demon.run import run_campaign


def test_rsi_real_demon_v3_integration() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    pack_path = repo_root / "campaigns" / "rsi_real_demon_v3" / "rsi_real_demon_campaign_pack_v3.json"
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "rsi_real_demon_v3"
        run_campaign(campaign_pack=pack_path, out_dir=out_dir, mode="real", strict=True)

        env = os.environ.copy()
        env["PYTHONPATH"] = str(repo_root / "CDEL-v2")
        cmd = [
            sys.executable,
            "-m",
            "cdel.v1_7r.verify_rsi_demon_v3",
            "--state_dir",
            str(out_dir),
        ]
        result = subprocess.run(cmd, env=env, check=False, capture_output=True, text=True)
        assert result.returncode == 0
        assert result.stdout.strip() == "VALID"
