from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping


def resolve_path(path_str: str, base: Path) -> Path:
    path = Path(path_str)
    if path.is_absolute():
        return path
    if path_str.startswith("genesis/"):
        path = Path(path_str[len("genesis/"):])
    return (base / path).resolve()


def normalize_config_paths(config: Mapping[str, object], base: Path, keys: Iterable[str]) -> dict:
    normalized = dict(config)
    for key in keys:
        value = normalized.get(key)
        if isinstance(value, str):
            normalized[key] = str(resolve_path(value, base))
    return normalized
