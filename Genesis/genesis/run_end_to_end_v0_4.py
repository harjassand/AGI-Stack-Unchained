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

from genesis.capsules.world_model_builder import build_world_model_capsule  # noqa: E402
from genesis.core.world_model_search import seed_model_specs  # noqa: E402
from genesis.promotion.server_manager import start_server, stop_server  # noqa: E402


def _resolve_path(path_str: str) -> Path:
    path = Path(path_str)
    if path.is_absolute():
        return path
    if path_str.startswith("genesis/"):
        path = Path(path_str[len("genesis/"):])
    return (ROOT / path).resolve()


def _load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def main() -> int:
    parser = argparse.ArgumentParser(description="Genesis end-to-end v0.4 run")
    parser.add_argument("--config", default=str(ROOT / "configs" / "world_model.json"))
    args = parser.parse_args()

    cdel_root = os.getenv("CDEL_ROOT")
    if not cdel_root:
        raise SystemExit("CDEL_ROOT is required")

    config_path = _resolve_path(args.config)
    if not config_path.exists():
        raise SystemExit(f"config not found: {config_path}")

    config = _load_config(config_path)
    epoch_id = config.get("epoch_id", "epoch-1")
    ledger_dir = Path(os.getenv("LEDGER_DIR", str(ROOT / ".cdel_ledger_e2e_v0_4")))

    seed_specs = seed_model_specs(config)
    allow_capsule = build_world_model_capsule(seed_specs[0], config)
    allowlist = allow_capsule["capsule_id"]

    handle = start_server(
        cdel_root=Path(cdel_root),
        ledger_dir=ledger_dir,
        fixture_dir=Path(cdel_root),
        epoch_id=epoch_id,
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
            ["python3", str(ROOT / "world_model_run.py"), "--config", str(config_path)],
            check=True,
            env=env,
        )
    finally:
        stop_server(handle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
