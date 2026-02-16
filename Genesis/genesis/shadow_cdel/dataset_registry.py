from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Optional


@dataclass
class DatasetHandle:
    dataset_id: str
    path: Path
    format: str


def _load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def _resolve_path(path: Path, base_dir: Path) -> Optional[Path]:
    try:
        resolved = path.resolve()
        resolved.relative_to(base_dir.resolve())
    except Exception:
        return None
    return resolved


class DatasetRegistry:
    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self.base_dir = config_path.parent.parent
        self._config = _load_config(config_path)

    def resolve(self, dataset_id: str) -> Optional[DatasetHandle]:
        datasets = self._config.get("datasets", {})
        spec = datasets.get(dataset_id)
        if spec is None:
            return None
        rel_path = Path(spec.get("path", ""))
        resolved = _resolve_path(self.base_dir / rel_path, self.base_dir)
        if resolved is None or not resolved.exists():
            return None
        return DatasetHandle(
            dataset_id=dataset_id,
            path=resolved,
            format=str(spec.get("format", "jsonl")),
        )
