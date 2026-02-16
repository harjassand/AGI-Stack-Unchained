#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(ROOT.parent))

from genesis.core.codesign import run_codesign  # noqa: E402
from genesis.promotion.server_manager import start_server, stop_server  # noqa: E402


def _load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def main() -> int:
    parser = argparse.ArgumentParser(description="Genesis end-to-end v0.6 run")
    parser.add_argument("--system-config", default="genesis/configs/system.json")
    args = parser.parse_args()

    cdel_root = os.getenv("CDEL_ROOT")
    if not cdel_root:
        raise SystemExit("CDEL_ROOT is required")

    config = _load_config(Path(args.system_config))
    epoch_id = config.get("epoch_id", "epoch-1")
    ledger_dir = Path(os.getenv("LEDGER_DIR", "genesis/.cdel_ledger_e2e_v0_6"))
    component_store_dir = Path(config.get("component_store_dir", "genesis/components"))

    preflight = run_codesign(config)
    allowlist = ",".join([event.system_capsule["capsule_id"] for event in preflight["events"]])

    handle = start_server(
        cdel_root=Path(cdel_root),
        ledger_dir=ledger_dir,
        fixture_dir=Path(cdel_root),
        epoch_id=epoch_id,
        component_store_dir=component_store_dir,
        env_overrides={
            "CDEL_PASS_CAPSULE_IDS": allowlist,
            "CDEL_EPSILON_TOTAL": "2",
            "CDEL_DELTA_TOTAL": "0",
        },
    )
    try:
        env = os.environ.copy()
        env["CDEL_URL"] = f"{handle.base_url}/evaluate"
        subprocess.run(
            ["python3", str(ROOT / "system_run.py"), "--config", str(Path(args.system_config))],
            check=True,
            env=env,
        )
    finally:
        stop_server(handle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
