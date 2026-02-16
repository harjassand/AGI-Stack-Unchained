from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v18_0.omega_common_v1 import OmegaV18Error, canon_hash_obj, hash_bytes, tree_hash


def _reference_tree_hash(root: Path) -> str:
    files: list[dict[str, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        files.append({"path": rel, "sha256": hash_bytes(path.read_bytes())})
    return canon_hash_obj({"schema_version": "omega_tree_hash_v1", "files": files})


def _seed_large_tree(root: Path) -> None:
    for i in range(24):
        for j in range(12):
            dir_path = root / f"dir_{i:03d}" / f"nested_{j:03d}" / "leaf"
            dir_path.mkdir(parents=True, exist_ok=True)
            for k in range(3):
                idx = ((i * 12) + j) * 3 + k
                payload = (f"{i:03d}:{j:03d}:{k:02d}\n".encode("utf-8")) * ((idx % 7) + 1)
                (dir_path / f"small_{k:02d}.txt").write_bytes(payload)

    (root / "large").mkdir(parents=True, exist_ok=True)
    (root / "large" / "blob_a.bin").write_bytes((b"abcdefgh01234567" * (8 * 1024 * 1024 // 16)))
    (root / "large" / "blob_b.bin").write_bytes((b"01234567hgfedcba" * (5 * 1024 * 1024 // 16)))


def test_tree_hash_fast_matches_reference_large(tmp_path) -> None:
    root = tmp_path / "tree"
    _seed_large_tree(root)

    expected = _reference_tree_hash(root)
    observed = tree_hash(root)

    assert observed == expected


def test_tree_hash_rejects_symlink(tmp_path) -> None:
    root = tmp_path / "tree"
    root.mkdir(parents=True, exist_ok=True)
    (root / "data.txt").write_text("hello\n", encoding="utf-8")
    (root / "link.txt").symlink_to(root / "data.txt")

    with pytest.raises(OmegaV18Error, match="SCHEMA_FAIL"):
        tree_hash(root)
