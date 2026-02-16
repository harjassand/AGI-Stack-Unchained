#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = [
    "active_bundle_hash",
    "prev_active_bundle_hash",
    "kernel_hash",
    "meta_hash",
    "ruleset_hash",
    "toolchain_merkle_root",
    "ledger_head_hash",
]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _is_hex64(value: str) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    for ch in value:
        if ch not in "0123456789abcdef":
            return False
    return True


def _receipt_paths(epoch_dir: Path) -> list[Path]:
    receipts_dir = epoch_dir / "receipts"
    if receipts_dir.exists():
        return sorted(receipts_dir.glob("*/receipt.json"))
    return sorted(epoch_dir.glob("**/receipt.json"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify meta-core fields in CAOE receipts.")
    parser.add_argument("epoch_dir", help="Epoch directory containing receipts/")
    args = parser.parse_args()

    epoch_dir = Path(args.epoch_dir).resolve()
    receipt_paths = _receipt_paths(epoch_dir)
    if not receipt_paths:
        print(f"no receipts found under {epoch_dir}", file=sys.stderr)
        return 2

    errors: list[str] = []
    for receipt_path in receipt_paths:
        receipt = _load_json(receipt_path)
        if str(receipt.get("decision") or "") != "PASS":
            continue
        meta = receipt.get("meta_core") or {}
        for key in REQUIRED_FIELDS:
            if key not in meta:
                errors.append(f"{receipt_path}: missing meta_core.{key}")
                continue
            value = meta.get(key)
            if key == "prev_active_bundle_hash" and value == "":
                continue
            if not _is_hex64(str(value)):
                errors.append(f"{receipt_path}: invalid meta_core.{key}={value}")

    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
