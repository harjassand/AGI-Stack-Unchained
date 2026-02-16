#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(ROOT.parent))

from genesis.promotion.server_manager import start_server, stop_server  # noqa: E402


def _resolve_path(path_str: str) -> Path:
    path = Path(path_str)
    if path.is_absolute():
        return path
    if path_str.startswith("genesis/"):
        path = Path(path_str[len("genesis/"):])
    return (ROOT / path).resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description="Genesis end-to-end v0.3 run")
    parser.add_argument("--config", default=str(ROOT / "configs" / "default.json"))
    args = parser.parse_args()

    cdel_root = os.getenv("CDEL_ROOT")
    if not cdel_root:
        raise SystemExit("CDEL_ROOT is required")

    config_path = _resolve_path(args.config)
    if not config_path.exists():
        raise SystemExit(f"config not found: {config_path}")

    epoch_id = "epoch-1"
    ledger_dir = Path(os.getenv("LEDGER_DIR", str(ROOT / ".cdel_ledger_e2e_v0_3")))
    handle = start_server(
        cdel_root=Path(cdel_root),
        ledger_dir=ledger_dir,
        fixture_dir=Path(cdel_root),
        epoch_id=epoch_id,
    )
    try:
        env = os.environ.copy()
        env["CDEL_URL"] = f"{handle.base_url}/evaluate"
        subprocess.run(
            ["python3", str(ROOT / "genesis_run.py"), "--config", str(config_path)],
            check=True,
            env=env,
        )
    finally:
        stop_server(handle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
