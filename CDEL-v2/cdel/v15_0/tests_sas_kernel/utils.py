from __future__ import annotations

from pathlib import Path

from cdel.v1_7r.canon import write_canon_json


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(path, payload)
