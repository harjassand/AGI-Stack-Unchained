"""Omega promotion bundle helpers (v18 top-level evidence)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .omega_common_v1 import canon_hash_obj, fail, load_canon_dict, require_relpath


def load_bundle(path: Path) -> tuple[dict[str, Any], str]:
    obj = load_canon_dict(path)
    return obj, canon_hash_obj(obj)


def extract_touched_paths(bundle: dict[str, Any]) -> list[str]:
    out: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"path", "file", "relpath", "target_rel"} and isinstance(item, str):
                    out.append(item)
                elif key in {"paths", "files", "touched_paths", "patch_paths"} and isinstance(item, list):
                    for row in item:
                        if isinstance(row, str):
                            out.append(row)
                walk(item)
        elif isinstance(value, list):
            for row in value:
                walk(row)

    walk(bundle)
    cleaned: list[str] = []
    for row in out:
        try:
            cleaned.append(require_relpath(row))
        except Exception:  # noqa: BLE001
            continue
    return sorted(set(cleaned))


__all__ = ["extract_touched_paths", "load_bundle"]
