#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

CDEL_ROOT = Path(__file__).resolve().parents[2]
if (CDEL_ROOT / "cdel").is_dir():
    sys.path.insert(0, str(CDEL_ROOT))

from cdel.canon.json_canon_v1 import canon_bytes, loads, sha256_hex


def _load_json(path: Path) -> dict[str, Any]:
    data = loads(path.read_bytes())
    if not isinstance(data, dict):
        raise SystemExit(f"expected JSON object: {path}")
    return data


def _hash_file(path: Path) -> str:
    return sha256_hex(path.read_bytes())


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise SystemExit(msg)


def _verify_manifest(out_dir: Path) -> dict[str, Any]:
    manifest_path = out_dir / "mind_v2_rsi_success_manifest.json"
    _assert(manifest_path.is_file(), f"missing manifest: {manifest_path}")
    raw = manifest_path.read_bytes()
    parsed = loads(raw)
    _assert(isinstance(parsed, dict), "manifest must be JSON object")
    canon = canon_bytes(parsed)
    _assert(raw == canon, "manifest not canonical")

    sha_path = out_dir / "mind_v2_rsi_success_manifest_sha256.txt"
    _assert(sha_path.is_file(), f"missing manifest sha file: {sha_path}")
    expected = sha_path.read_text(encoding="utf-8").strip()
    actual = sha256_hex(raw)
    _assert(expected == actual, "manifest sha256 mismatch")
    return parsed


def _verify_receipts(run_dir: Path) -> None:
    for eval_path in run_dir.rglob("eval_result.json"):
        result = _load_json(eval_path)
        status = result.get("status")
        receipt = eval_path.parent / "receipt.json"
        if status == "PASS":
            _assert(receipt.exists(), f"receipt missing for PASS: {eval_path}")
        else:
            _assert(not receipt.exists(), f"receipt present for FAIL: {eval_path}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="verify-out-dir-mind-v2-rsi")
    parser.add_argument("out_dir")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    _assert(out_dir.is_dir(), f"missing out_dir: {out_dir}")

    manifest = _verify_manifest(out_dir)

    rsi_dir = out_dir / "rsi"
    _assert(rsi_dir.is_dir(), f"missing rsi dir: {rsi_dir}")
    metrics = _load_json(rsi_dir / "rsi_metrics.json")
    _assert(metrics.get("format") == "ccai_x_mind_rsi_metrics_v3", "unexpected rsi metrics format")

    epochs = metrics.get("epochs", [])
    _assert(any(ep.get("improved") for ep in epochs), "no improvement event recorded")

    _verify_receipts(rsi_dir)

    receipts = manifest.get("receipt_hashes", [])
    if receipts:
        for entry in receipts:
            rel = Path(entry.get("path", ""))
            sha = entry.get("sha256", "")
            path = rsi_dir / rel
            _assert(path.is_file(), f"missing receipt referenced in manifest: {path}")
            _assert(_hash_file(path) == sha, f"receipt hash mismatch: {path}")

    print("PASS")


if __name__ == "__main__":
    main()
