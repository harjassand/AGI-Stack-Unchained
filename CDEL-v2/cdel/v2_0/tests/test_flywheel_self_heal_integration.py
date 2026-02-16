from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def test_flywheel_self_heal_integration() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    flywheel_pack = repo_root / "campaigns" / "rsi_real_flywheel_v2_0" / "rsi_real_flywheel_pack_v1.json"

    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "flywheel_run"

        env = os.environ.copy()
        env["PYTHONPATH"] = str(repo_root / "Extension-1" / "agi-orchestrator")

        cmd = [
            sys.executable,
            "-m",
            "orchestrator.rsi_flywheel_v2",
            "--flywheel_pack",
            str(flywheel_pack),
            "--out_dir",
            str(out_dir),
        ]
        result = subprocess.run(cmd, env=env, check=False, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        out = result.stdout.strip()
        assert out == "VALID"
