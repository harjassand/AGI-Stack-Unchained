#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from cdel.canon.json_canon_v1 import canon_bytes, loads, sha256_hex


def _hash_file(path: Path) -> str:
    return sha256_hex(path.read_bytes())


def _load_manifest(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    obj = loads(raw)
    if canon_bytes(obj) != raw:
        raise SystemExit(f"manifest not canonical: {path}")
    if not isinstance(obj, dict):
        raise SystemExit(f"manifest must be object: {path}")
    return obj


def _verify_run(out_root: Path, run_root: str, run_info: dict[str, Any]) -> None:
    run_dir = out_root / "runs" / run_root / run_info["run_label"]
    eval_result_path = run_dir / "eval_result.json"
    if _hash_file(eval_result_path) != run_info.get("eval_result_sha256"):
        raise SystemExit(f"eval_result hash mismatch: {run_dir}")

    receipt_sha = run_info.get("receipt_sha256", "")
    receipt_path = run_dir / "receipt.json"
    if receipt_sha:
        if not receipt_path.exists():
            raise SystemExit(f"receipt missing: {run_dir}")
        if _hash_file(receipt_path) != receipt_sha:
            raise SystemExit(f"receipt hash mismatch: {run_dir}")
    else:
        if receipt_path.exists():
            raise SystemExit(f"receipt present on missing hash: {run_dir}")

    for entry in run_info.get("evidence_sha256", []):
        path = run_dir / entry["path"]
        if _hash_file(path) != entry.get("sha256"):
            raise SystemExit(f"evidence hash mismatch: {path}")


def _verify_fail_fixture(out_root: Path, run_root: str, fixture: dict[str, Any]) -> None:
    status = fixture.get("status")
    if status != "FAIL":
        raise SystemExit("fixture status not FAIL")
    if fixture.get("fail_code") != fixture.get("expected_fail_code"):
        raise SystemExit("fixture fail code mismatch")
    receipt_sha = fixture.get("receipt_sha256", "")
    if receipt_sha:
        raise SystemExit("fixture receipt present")
    _verify_run(out_root, run_root, fixture)


def main() -> int:
    parser = argparse.ArgumentParser(prog="ccai-x-mind-proof-verify")
    parser.add_argument("--out_dir", required=True)
    parser.add_argument("--expected_failures", default=None)
    args = parser.parse_args()

    out_root = Path(args.out_dir).resolve()
    m1 = _load_manifest(out_root / "proof_manifest_run1.json")
    m2 = _load_manifest(out_root / "proof_manifest_run2.json")

    if canon_bytes(m1) != canon_bytes(m2):
        raise SystemExit("manifest mismatch between run1 and run2")

    determinism = m1.get("determinism", {})
    if not determinism.get("determinism_ok"):
        raise SystemExit("determinism_ok false")

    for run in (m1.get("runs") or {}).values():
        _verify_run(out_root, "run1", run)
        _verify_run(out_root, "run2", run)

    fail_fixtures = m1.get("fail_fixtures", {})
    if args.expected_failures:
        expected = json.loads(Path(args.expected_failures).read_text(encoding="utf-8"))
        for key, code in expected.items():
            fixture = fail_fixtures.get(key)
            if not fixture:
                raise SystemExit(f"missing fixture in manifest: {key}")
            fixture["expected_fail_code"] = code

    for fixture in fail_fixtures.values():
        _verify_fail_fixture(out_root, "run1", fixture)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
