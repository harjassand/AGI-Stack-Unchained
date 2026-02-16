from __future__ import annotations

from pathlib import Path

from cdel.v1_7r.canon import canon_bytes, sha256_prefixed
from cdel.v2_3.immutable_core import load_lock, validate_receipt


def test_meta_core_receipt_schema_and_hash() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    lock_path = repo_root / "meta-core" / "meta_constitution" / "v2_3" / "immutable_core_lock_v1.json"
    lock = load_lock(lock_path)

    receipt = {
        "schema": "immutable_core_receipt_v1",
        "spec_version": "v2_3",
        "verdict": "VALID",
        "reason": "OK",
        "repo_root_sha256": sha256_prefixed(str(repo_root).encode("utf-8")),
        "lock_path": str(lock_path.relative_to(repo_root)).replace("\\", "/"),
        "lock_id": lock["lock_id"],
        "core_id_expected": lock["core_id"],
        "core_id_observed": lock["core_id"],
        "mismatches": [],
        "receipt_head_hash": "__SELF__",
    }
    head = dict(receipt)
    head.pop("receipt_head_hash", None)
    receipt["receipt_head_hash"] = sha256_prefixed(canon_bytes(head))

    validate_receipt(receipt, lock)
