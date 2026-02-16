#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(ROOT.parent))

from genesis.core.causal_search import run_causal_search  # noqa: E402
from genesis.capsules.canonicalize import capsule_hash  # noqa: E402
from genesis.capsules.receipt import verify_receipt  # noqa: E402
from genesis.promotion.server_manager import start_server, stop_server  # noqa: E402
from genesis.tools.path_utils import normalize_config_paths, resolve_path  # noqa: E402


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


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Genesis end-to-end v1.3 run")
    parser.add_argument("--causal-config", default=str(ROOT / "configs" / "causal_v1_3.json"))
    args = parser.parse_args()

    cdel_root = os.getenv("CDEL_ROOT")
    if not cdel_root:
        raise SystemExit("CDEL_ROOT is required")

    config = _load_config(resolve_path(args.causal_config, ROOT))
    config = normalize_config_paths(
        config,
        ROOT,
        keys=[
            "dataset_config",
            "run_log_path",
            "receipts_dir",
            "shadow_calibration_path",
            "protocol_budget_path",
        ],
    )
    epoch_id = config.get("epoch_id", "epoch-1")

    ledger_dir = Path(os.getenv("LEDGER_DIR", str(ROOT / ".cdel_ledger_e2e_v1_3")))
    receipts_dir = Path(config.get("receipts_dir", str(ROOT / "receipts_v1_3")))
    run_log_path = Path(config.get("run_log_path", str(ROOT.parent / "genesis_run_v1_3.jsonl")))
    protocol_budget_path = Path(config.get("protocol_budget_path", str(receipts_dir / "protocol_budget.json")))
    calibration_path = Path(config.get("shadow_calibration_path", str(ROOT / "shadow_calibration_v1_3.json")))

    preflight = run_causal_search(config)
    allowlist = ",".join([event.capsule["capsule_id"] for event in preflight["events"]])
    capsule_by_hash = {capsule_hash(event.capsule): event.capsule for event in preflight["events"]}

    log_hashes = []
    for _ in range(2):
        for path in [ledger_dir, receipts_dir, run_log_path, protocol_budget_path, calibration_path]:
            _clean_path(path)

        handle = start_server(
            cdel_root=Path(cdel_root),
            ledger_dir=ledger_dir,
            fixture_dir=Path(cdel_root),
            epoch_id=epoch_id,
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
            subprocess.run(
                ["python3", str(ROOT / "causal_run.py"), "--config", str(resolve_path(args.causal_config, ROOT))],
                check=True,
                env=env,
            )
        finally:
            stop_server(handle)

        records = _read_log(run_log_path)
        if not records:
            raise SystemExit("genesis_run_v1_3.jsonl was empty")

        promotion_records = [record for record in records if record.get("promotion_result") == "PASS"]
        if not promotion_records:
            raise SystemExit("expected at least one PASS promotion in run log")

        receipt_index = receipts_dir / "receipts.jsonl"
        if not receipt_index.exists():
            raise SystemExit("receipt index missing")
        receipt_entries = [
            json.loads(line)
            for line in receipt_index.read_text(encoding="utf-8").splitlines()
            if line
        ]
        if not receipt_entries:
            raise SystemExit("receipt index empty")

        pass_record = promotion_records[0]
        pass_capsule_hash = str(pass_record.get("capsule_hash", ""))
        capsule = capsule_by_hash.get(pass_capsule_hash)
        if capsule is None:
            raise SystemExit("PASS capsule hash not found in preflight")
        receipt_id = receipt_entries[-1].get("receipt_hash_raw", "")
        receipt_path = receipts_dir / f"receipt_{receipt_id}.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        ok, err = verify_receipt(receipt, capsule, epoch_id)
        if not ok:
            raise SystemExit(f"receipt verification failed: {err}")

        log_hashes.append(_hash_file(run_log_path))

    if len(set(log_hashes)) != 1:
        raise SystemExit("run log hashes differ across runs")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
