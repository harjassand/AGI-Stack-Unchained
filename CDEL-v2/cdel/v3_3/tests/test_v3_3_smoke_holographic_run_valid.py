from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from cdel.v3_3.verify_rsi_swarm_v4 import verify


def test_v3_3_smoke_holographic_run_valid(tmp_path, repo_root: Path) -> None:
    out_dir = tmp_path / "run"
    pack_path = repo_root / "campaigns" / "rsi_real_swarm_v3_3" / "rsi_real_swarm_pack_v4.json"

    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [
            str(repo_root / "Extension-1" / "agi-orchestrator"),
            str(repo_root / "CDEL-v2"),
        ]
    )

    subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator.rsi_swarm_v3_3",
            "--swarm_pack",
            str(pack_path),
            "--out_dir",
            str(out_dir),
        ],
        check=True,
        env=env,
        cwd=str(repo_root),
    )

    receipt = verify(out_dir)
    assert receipt["verdict"] == "VALID"
