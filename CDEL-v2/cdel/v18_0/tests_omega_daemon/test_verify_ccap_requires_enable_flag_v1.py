from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_verify_ccap_cli_requires_enable_flag() -> None:
    cmd = [
        sys.executable,
        "-m",
        "cdel.v18_0.verify_ccap_v1",
        "--mode",
        "full",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode == 1
    assert "INVALID:CCAP_DISABLED" in result.stdout
