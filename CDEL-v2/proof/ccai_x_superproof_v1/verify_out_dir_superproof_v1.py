#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
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
    manifest_path = out_dir / "super_manifest_v1.json"
    _assert(manifest_path.is_file(), f"missing manifest: {manifest_path}")
    raw = manifest_path.read_bytes()
    parsed = loads(raw)
    _assert(isinstance(parsed, dict), "manifest must be JSON object")
    canon = canon_bytes(parsed)
    _assert(raw == canon, "super manifest not canonical")

    sha_path = out_dir / "super_manifest_sha256.txt"
    _assert(sha_path.is_file(), f"missing manifest sha file: {sha_path}")
    expected = sha_path.read_text(encoding="utf-8").strip()
    actual = sha256_hex(raw)
    _assert(expected == actual, "super manifest sha256 mismatch")
    return parsed


def _verify_subverifier(name: str, path: str, run_dir: Path) -> None:
    if name == "mind_v1_baseline":
        cmd = ["python3", path, "--out_dir", str(run_dir)]
    else:
        cmd = ["python3", path, str(run_dir)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"sub-verifier failed for {name}: {result.stderr.strip()}")


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
    parser = argparse.ArgumentParser(prog="verify-out-dir-superproof")
    parser.add_argument("out_dir")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    _assert(out_dir.is_dir(), f"missing out_dir: {out_dir}")

    manifest = _verify_manifest(out_dir)

    verifier_sha = manifest.get("verifier_sha256", {})
    if not isinstance(verifier_sha, dict):
        raise SystemExit("verifier_sha256 not an object")

    repo_root = Path(__file__).resolve().parents[3]
    verifier_paths = {
        "mind_v1_baseline": repo_root / "CDEL-v2" / "proof" / "ccai_x_mind_v1" / "verify_ccai_x_mind_v1.py",
        "mind_v1_ext2": repo_root / "CDEL-v2" / "proof" / "ccai_x_mind_v1_ext2" / "verify_out_dir_ext2_v1.py",
        "mind_v2_structure": repo_root / "CDEL-v2" / "proof" / "ccai_x_mind_v2" / "verify_out_dir_mind_v2_v1.py",
        "mind_v2_rsi": repo_root / "CDEL-v2" / "proof" / "ccai_x_mind_v2" / "verify_out_dir_mind_v2_rsi_v1.py",
        "superproof": repo_root / "CDEL-v2" / "proof" / "ccai_x_superproof_v1" / "verify_out_dir_superproof_v1.py",
    }
    for name, path in verifier_paths.items():
        _assert(name in verifier_sha, f"verifier hash missing for {name}")
        if not path.is_file():
            raise SystemExit(f"verifier path missing: {path}")
        actual = _hash_file(path)
        expected = str(verifier_sha.get(name))
        _assert(actual == expected, f"verifier hash mismatch for {name}")

    baseline_dir = out_dir / "mind_v1_baseline"
    ext2_dir = out_dir / "mind_v1_ext2"
    mind_v2_dir = out_dir / "mind_v2"
    mind_v2_rsi_dir = out_dir / "mind_v2_rsi"

    _assert(baseline_dir.is_dir(), f"missing baseline dir: {baseline_dir}")
    _assert(ext2_dir.is_dir(), f"missing ext2 dir: {ext2_dir}")
    _assert(mind_v2_dir.is_dir(), f"missing mind v2 dir: {mind_v2_dir}")

    _verify_subverifier("mind_v1_baseline", str(verifier_paths["mind_v1_baseline"]), baseline_dir)
    _verify_subverifier("mind_v1_ext2", str(verifier_paths["mind_v1_ext2"]), ext2_dir)
    _verify_subverifier("mind_v2_structure", str(verifier_paths["mind_v2_structure"]), mind_v2_dir)

    _assert(mind_v2_rsi_dir.is_dir(), f"missing mind_v2_rsi dir: {mind_v2_rsi_dir}")
    _verify_subverifier("mind_v2_rsi", str(verifier_paths["mind_v2_rsi"]), mind_v2_rsi_dir)

    manifests = manifest.get("manifests", {})
    if isinstance(manifests, dict):
        for name, entry in manifests.items():
            if not isinstance(entry, dict):
                continue
            rel = Path(entry.get("path", ""))
            sha = entry.get("sha256", "")
            path = out_dir / rel
            _assert(path.is_file(), f"missing manifest referenced in super_manifest: {path}")
            _assert(_hash_file(path) == sha, f"manifest hash mismatch for {name}")

    _verify_receipts(baseline_dir)
    _verify_receipts(ext2_dir)
    _verify_receipts(mind_v2_dir)
    _verify_receipts(mind_v2_rsi_dir)

    # Verify receipt hashes recorded in manifest
    receipts = manifest.get("receipt_hashes", {})
    if isinstance(receipts, dict):
        for group, entries in receipts.items():
            if not isinstance(entries, list):
                continue
            base = out_dir / group if group != "mind_v2_rsi" else mind_v2_rsi_dir
            if group == "mind_v1_baseline":
                base = baseline_dir
            elif group == "mind_v1_ext2":
                base = ext2_dir
            elif group == "mind_v2_structure":
                base = mind_v2_dir
            for entry in entries:
                rel = Path(entry.get("path", ""))
                sha = entry.get("sha256", "")
                path = base / rel
                _assert(path.is_file(), f"missing receipt referenced in manifest: {path}")
                _assert(_hash_file(path) == sha, f"receipt hash mismatch: {path}")

    # Baseline non-regression check via ext2 + mind v2 receipt hashes
    ext2_baseline = manifest.get("baseline_receipts_ext2")
    if isinstance(ext2_baseline, dict):
        path = out_dir / ext2_baseline.get("path", "")
        _assert(path.is_file(), f"missing ext2 baseline receipts: {path}")
        _assert(_hash_file(path) == ext2_baseline.get("sha256", ""), "ext2 baseline receipts hash mismatch")

    mind_v2_baseline = manifest.get("baseline_receipts_mind_v2")
    if isinstance(mind_v2_baseline, dict):
        path = out_dir / mind_v2_baseline.get("path", "")
        _assert(path.is_file(), f"missing mind v2 baseline receipts: {path}")
        _assert(_hash_file(path) == mind_v2_baseline.get("sha256", ""), "mind v2 baseline receipts hash mismatch")

    print("PASS")


if __name__ == "__main__":
    main()
