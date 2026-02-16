from __future__ import annotations

from pathlib import Path

from cdel.v2_2.code_patch import tree_hash_v1
from cdel.v2_2.constants import require_constants


def test_csi_tree_hash_deterministic(tmp_path: Path) -> None:
    constants = require_constants()
    allowed_roots = list(constants.get("CSI_ALLOWED_ROOTS", []))
    immutable_paths = list(constants.get("CSI_IMMUTABLE_PATHS", []))
    assert allowed_roots

    root = tmp_path
    allowed_root = root / allowed_roots[0]
    allowed_root.mkdir(parents=True, exist_ok=True)

    (allowed_root / "b.txt").write_text("beta", encoding="utf-8")
    (allowed_root / "a.txt").write_text("alpha", encoding="utf-8")

    h1 = tree_hash_v1(root, allowed_roots, immutable_paths)
    h2 = tree_hash_v1(root, allowed_roots, immutable_paths)
    assert h1 == h2
