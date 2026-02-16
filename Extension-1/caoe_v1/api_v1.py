"""CAOE v1 proposer shared helpers."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def bootstrap_paths() -> Path:
    """Ensure CAOE v1 subdirectories are importable.

    Returns the base directory path.
    """
    base_dir = Path(__file__).resolve().parent
    subdirs = [
        base_dir,
        base_dir / "state",
        base_dir / "wake",
        base_dir / "sleep",
        base_dir / "sleep" / "operators",
        base_dir / "sleep" / "synth",
        base_dir / "dawn",
        base_dir / "artifacts",
        base_dir / "cli",
    ]
    for path in subdirs:
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)
    return base_dir


def canonical_json_bytes(obj: Any) -> bytes:
    """Return canonical JSON bytes (UTF-8, sorted keys, minimal separators, LF)."""
    text = json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return text.encode("utf-8")


def load_json(path: str | Path) -> Any:
    path = Path(path)
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: str | Path, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def atomic_write_json(path: str | Path, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    os.replace(tmp_path, path)


def ensure_dir(path: str | Path) -> Path:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path
