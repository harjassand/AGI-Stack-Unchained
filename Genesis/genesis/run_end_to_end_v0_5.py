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
from genesis.capsules.policy_builder import build_policy_capsule  # noqa: E402
from genesis.core.world_model_search import seed_model_specs  # noqa: E402
from genesis.core.planning import plan_policy_from_model  # noqa: E402
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
    parser = argparse.ArgumentParser(description="Genesis end-to-end v0.5 run")
    parser.add_argument("--world-model-config", default=str(ROOT / "configs" / "world_model.json"))
    parser.add_argument("--policy-config", default=str(ROOT / "configs" / "policy.json"))
    args = parser.parse_args()

    cdel_root = os.getenv("CDEL_ROOT")
    if not cdel_root:
        raise SystemExit("CDEL_ROOT is required")

    world_model_config = _load_config(_resolve_path(args.world_model_config))
    policy_config = _load_config(_resolve_path(args.policy_config))
    epoch_id = world_model_config.get("epoch_id", "epoch-1")
    ledger_dir = Path(os.getenv("LEDGER_DIR", str(ROOT / ".cdel_ledger_e2e_v0_5")))

    wm_seed_spec = seed_model_specs(world_model_config)[0]
    wm_capsule = build_world_model_capsule(wm_seed_spec, world_model_config)
    planning_model_spec = policy_config.get("planning_model_spec") or {"model_family": "logistic_regression", "weights": [1.0], "bias": 0.0}
    planned_policy_spec = plan_policy_from_model(planning_model_spec, policy_config)
    policy_capsule = build_policy_capsule(planned_policy_spec, policy_config)
    allowlist = ",".join([wm_capsule["capsule_id"], policy_capsule["capsule_id"]])

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
            ["python3", str(ROOT / "world_model_run.py"), "--config", str(_resolve_path(args.world_model_config))],
            check=True,
            env=env,
        )
        subprocess.run(
            ["python3", str(ROOT / "policy_run.py"), "--config", str(_resolve_path(args.policy_config))],
            check=True,
            env=env,
        )
    finally:
        stop_server(handle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
