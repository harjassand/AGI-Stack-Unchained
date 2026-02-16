from __future__ import annotations

from pathlib import Path

from cdel.v2_3.immutable_core import compute_core_tree_hash, compute_lock_head_hash, compute_lock_id, load_lock


def test_immutable_core_lock_hashing_stable() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    lock_path = repo_root / "meta-core" / "meta_constitution" / "v2_3" / "immutable_core_lock_v1.json"
    lock = load_lock(lock_path)

    assert compute_core_tree_hash(lock["files"]) == lock["core_tree_hash_v1"]
    assert lock["core_id"] == lock["core_tree_hash_v1"]
    assert compute_lock_id(lock) == lock["lock_id"]
    assert compute_lock_head_hash(lock) == lock["lock_head_hash"]
