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
from genesis.tools.release_pack import build_release_pack  # noqa: E402
from genesis.tools.verify_release_pack import verify_release_pack  # noqa: E402


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


def _find_pass_capsule_hash(records: list[dict]) -> str:
    for record in records:
        if record.get("promotion_result") == "PASS":
            return str(record.get("system_hash", ""))
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Genesis end-to-end v1.0 run")
    parser.add_argument("--system-config", default="genesis/configs/system_v1_0.json")
    args = parser.parse_args()

    cdel_root = os.getenv("CDEL_ROOT")
    if not cdel_root:
        raise SystemExit("CDEL_ROOT is required")

    config = _load_config(Path(args.system_config))
    epoch_id = config.get("epoch_id", "epoch-1")

    ledger_dir = Path(os.getenv("LEDGER_DIR", "genesis/.cdel_ledger_e2e_v1_0"))
    receipts_dir = Path(config.get("receipts_dir", "genesis/receipts_v1_0"))
    component_store_dir = Path(config.get("component_store_dir", "genesis/components_v1_0"))
    calibration_path = Path(config.get("shadow_calibration_path", "genesis/shadow_calibration_v1_0.json"))
    run_log_path = Path(config.get("run_log_path", "genesis_run_v1_0.jsonl"))
    protocol_budget_path = Path(config.get("protocol_budget_path", receipts_dir / "protocol_budget.json"))
    release_pack_dir = Path(config.get("release_pack_dir", "genesis/release_packs_v1_0"))

    _clean_path(ledger_dir)
    _clean_path(receipts_dir)
    _clean_path(component_store_dir)
    _clean_path(calibration_path)
    _clean_path(run_log_path)
    _clean_path(protocol_budget_path)
    _clean_path(release_pack_dir)

    keystore_path = Path("genesis/cdel_keystore_v1_0.json")
    _clean_path(keystore_path)
    gen_env = os.environ.copy()
    gen_env["PYTHONPATH"] = str(Path(cdel_root))
    subprocess.run(
        [
            "python3",
            str(Path(cdel_root) / "tools" / "gen_signing_key.py"),
            "--keystore",
            str(keystore_path),
            "--overwrite",
        ],
        check=True,
        env=gen_env,
    )

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
            "CDEL_RECEIPT_KEYSTORE": str(keystore_path),
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

    records = _read_log(run_log_path)
    if not records:
        raise SystemExit("genesis_run_v1_0.jsonl was empty")

    system_hash = _find_pass_capsule_hash(records)
    if not system_hash:
        raise SystemExit("expected at least one PASS promotion in run log")

    release_pack_dir.mkdir(parents=True, exist_ok=True)
    tar_path, _, _ = build_release_pack(
        capsule_hash_value=system_hash,
        component_store_dir=component_store_dir,
        receipts_dir=receipts_dir,
        ledger_dir=ledger_dir,
        out_dir=release_pack_dir,
    )
    verify_release_pack(tar_path, keystore_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
