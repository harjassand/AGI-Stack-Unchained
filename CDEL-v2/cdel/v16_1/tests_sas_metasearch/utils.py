from __future__ import annotations

import shutil
from pathlib import Path


def copy_run(src_run_root: Path, dst_run_root: Path) -> Path:
    if dst_run_root.exists():
        shutil.rmtree(dst_run_root)
    shutil.copytree(src_run_root, dst_run_root)
    return dst_run_root


def daemon_state(run_root: Path) -> Path:
    return run_root / "daemon" / "rsi_sas_metasearch_v16_1" / "state"
