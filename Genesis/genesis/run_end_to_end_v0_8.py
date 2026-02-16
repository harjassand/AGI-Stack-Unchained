#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
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


def _clean_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _read_log(path: Path) -> list[dict]:
    records = []
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Genesis end-to-end v0.8 run")
    parser.add_argument("--system-config", default="genesis/configs/system_v0_8.json")
    args = parser.parse_args()

    cdel_root = os.getenv("CDEL_ROOT")
    if not cdel_root:
        raise SystemExit("CDEL_ROOT is required")

    config = _load_config(Path(args.system_config))
    epoch_id = config.get("epoch_id", "epoch-1")

    ledger_dir = Path(os.getenv("LEDGER_DIR", "genesis/.cdel_ledger_e2e_v0_8"))
    receipts_dir = Path(config.get("receipts_dir", "genesis/receipts_v0_8"))
    component_store_dir = Path(config.get("component_store_dir", "genesis/components_v0_8"))
    calibration_path = Path(config.get("shadow_calibration_path", "genesis/shadow_calibration_v0_8.json"))
    run_log_path = Path(config.get("run_log_path", "genesis_run.jsonl"))
    protocol_budget_path = Path(config.get("protocol_budget_path", receipts_dir / "protocol_budget.json"))

    _clean_path(ledger_dir)
    _clean_path(receipts_dir)
    _clean_path(component_store_dir)
    _clean_path(calibration_path)
    _clean_path(run_log_path)
    _clean_path(protocol_budget_path)

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
            "CDEL_ALPHA_TOTAL": "0.001",
            "CDEL_EPSILON_TOTAL": "2",
            "CDEL_DELTA_TOTAL": "0",
        },
    )
    try:
        env = os.environ.copy()
        env["CDEL_URL"] = f"{handle.base_url}/evaluate"
        for _ in range(2):
            subprocess.run(
                ["python3", str(ROOT / "system_run.py"), "--config", str(Path(args.system_config))],
                check=True,
                env=env,
            )
    finally:
        stop_server(handle)

    records = _read_log(run_log_path)
    if not records:
        raise SystemExit("genesis_run.jsonl was empty")

    local_refusal = any(
        str(record.get("promotion_refusal_reason", "")).startswith("protocol_cap")
        for record in records
    )
    if not local_refusal:
        raise SystemExit("expected at least one protocol-cap refusal in run log")

    promotion_pass = any(record.get("promotion_result") == "PASS" for record in records)
    if not promotion_pass:
        raise SystemExit("expected at least one PASS promotion in run log")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
