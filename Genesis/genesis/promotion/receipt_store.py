from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from genesis.capsules.canonicalize import receipt_hash, receipt_log_hash, capsule_hash
from genesis.capsules.receipt import verify_receipt


def store_receipt(receipt: Dict, capsule: Dict, epoch_id: str, receipts_dir: Path) -> Dict:
    receipts_dir.mkdir(parents=True, exist_ok=True)
    capsule_h = capsule_hash(capsule)
    ok, err = verify_receipt(receipt, capsule, epoch_id)
    if not ok:
        raise ValueError(f"receipt verification failed: {err}")

    receipt_id = receipt_hash(receipt)
    log_hash = receipt_log_hash(receipt)
    receipt_path = receipts_dir / f"receipt_{receipt_id}.json"
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    index_path = receipts_dir / "receipts.jsonl"
    record = {
        "receipt_hash": log_hash,
        "receipt_hash_raw": receipt_id,
        "capsule_hash": capsule_h,
        "epoch_id": epoch_id,
        "audit_ref": receipt.get("x-audit_ref", ""),
    }
    with index_path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")

    return record
