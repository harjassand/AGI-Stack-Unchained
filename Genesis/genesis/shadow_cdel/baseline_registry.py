from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple


@dataclass
class BaselineMetric:
    value: float
    min_margin: float


class BaselineRegistry:
    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            path = Path(__file__).resolve().parents[1] / "configs" / "baselines.json"
        self.path = path
        self._cache: Dict[str, Dict[str, BaselineMetric]] | None = None

    def _load(self) -> Dict[str, Dict[str, BaselineMetric]]:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        data: Dict[str, Dict[str, BaselineMetric]] = {}
        for artifact_type, metrics in (raw or {}).items():
            typed: Dict[str, BaselineMetric] = {}
            for name, info in (metrics or {}).items():
                value = float(info.get("value", 0.0))
                min_margin = float(info.get("min_margin", 0.0))
                typed[str(name)] = BaselineMetric(value=value, min_margin=min_margin)
            data[str(artifact_type)] = typed
        return data

    def _ensure(self) -> Dict[str, Dict[str, BaselineMetric]]:
        if self._cache is None:
            self._cache = self._load()
        return self._cache

    def get(self, artifact_type: str, metric_name: str) -> Optional[BaselineMetric]:
        data = self._ensure()
        return data.get(artifact_type, {}).get(metric_name)
