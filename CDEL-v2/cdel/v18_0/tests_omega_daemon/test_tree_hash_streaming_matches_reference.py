from __future__ import annotations

from pathlib import Path

from cdel.v18_0.omega_common_v1 import canon_hash_obj, hash_bytes, tree_hash


def _reference_tree_hash(root: Path) -> str:
    files: list[dict[str, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        files.append({"path": rel, "sha256": hash_bytes(path.read_bytes())})
    return canon_hash_obj({"schema_version": "omega_tree_hash_v1", "files": files})


def test_tree_hash_streaming_matches_reference(tmp_path) -> None:
    root = tmp_path / "tree"
    (root / "small").mkdir(parents=True, exist_ok=True)
    (root / "nested" / "deep").mkdir(parents=True, exist_ok=True)

    (root / "small" / "a.txt").write_text("hello\n", encoding="utf-8")
    (root / "nested" / "deep" / "b.json").write_text('{"k":"v"}\n', encoding="utf-8")
    # ~10MB file to ensure the streaming code path is exercised.
    (root / "large.bin").write_bytes((b"0123456789abcdef" * (10 * 1024 * 1024 // 16)))

    expected = _reference_tree_hash(root)
    observed = tree_hash(root)

    assert observed == expected
