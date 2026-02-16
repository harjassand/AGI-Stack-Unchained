"""Immutable-tree snapshot helpers for SAS-System v14.0."""

from __future__ import annotations

from pathlib import Path

from ..v1_7r.canon import sha256_prefixed


def immutable_tree_snapshot(repo_root: Path) -> dict[str, object]:
    files: list[dict[str, str]] = []

    def add_file(path: Path) -> None:
        if path.is_file():
            rel = str(path.relative_to(repo_root))
            files.append({"path": rel, "sha256": sha256_prefixed(path.read_bytes())})

    meta_core = repo_root / "meta-core"
    if meta_core.exists():
        for path in sorted(meta_core.rglob("*")):
            add_file(path)

    cdel_root = repo_root / "CDEL-v2" / "cdel"
    if cdel_root.exists():
        for verify_path in sorted(cdel_root.glob("*/verify_*.py")):
            rel = str(verify_path.relative_to(repo_root))
            if rel == "CDEL-v2/cdel/v14_0/verify_rsi_sas_system_v1.py":
                continue
            add_file(verify_path)

    sealed_root = cdel_root / "sealed"
    if sealed_root.exists():
        for path in sorted(sealed_root.rglob("*")):
            add_file(path)

    schema_root = repo_root / "Genesis" / "schema"
    if schema_root.exists():
        for version_dir in sorted(schema_root.iterdir()):
            if not version_dir.is_dir():
                continue
            if version_dir.name == "v14_0":
                continue
            for path in sorted(version_dir.rglob("*")):
                add_file(path)

    files = sorted(files, key=lambda x: x["path"])
    return {
        "schema_version": "sas_system_immutable_tree_snapshot_v1",
        "spec_version": "v14_0",
        "files": files,
    }


__all__ = ["immutable_tree_snapshot"]
