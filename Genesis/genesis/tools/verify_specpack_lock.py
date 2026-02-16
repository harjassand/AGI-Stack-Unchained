#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from genesis.capsules import canonicalize  # noqa: E402

LOCK_PATH = ROOT / "specpack_lock.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_lock() -> dict:
    return json.loads(LOCK_PATH.read_text(encoding="utf-8"))


def main() -> int:
    lock = load_lock()

    expected_tag = lock.get("specpack_tag")
    if expected_tag != "v1.0.1":
        print("specpack_tag mismatch")
        return 1

    capsule_schema = ROOT / "capsules" / "schema" / "capsule.schema.json"
    receipt_schema = ROOT / "capsules" / "schema" / "receipt.schema.json"
    canon_tool = ROOT / "capsules" / "canonicalize.py"

    if sha256(capsule_schema) != lock.get("capsule_schema_sha256"):
        print("capsule schema hash mismatch")
        return 1
    if sha256(receipt_schema) != lock.get("receipt_schema_sha256"):
        print("receipt schema hash mismatch")
        return 1
    if sha256(canon_tool) != lock.get("canonicalization_tool_sha256"):
        print("canonicalization tool hash mismatch")
        return 1
    if canonicalize.CANON_ID.upper() != lock.get("canonicalization_id"):
        print("canonicalization id mismatch")
        return 1

    bundle_path = os.getenv("SPECPACK_BUNDLE_PATH")
    if bundle_path:
        if sha256(Path(bundle_path)) != lock.get("specpack_bundle_sha256"):
            print("specpack bundle hash mismatch")
            return 1

    tar_path = os.getenv("SPECPACK_TARBALL_PATH")
    if tar_path:
        if sha256(Path(tar_path)) != lock.get("specpack_tarball_sha256"):
            print("specpack tarball hash mismatch")
            return 1

    series_path = os.getenv("SPECPACK_LEVEL2_SERIES_SHA256")
    if series_path:
        series_hash = sha256(Path(series_path))
        if series_hash != lock.get("level2_fullstack_series_sha256"):
            print("level2 series hash mismatch")
            return 1

    print("specpack lock OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
