from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict


@dataclass
class CalibrationState:
    margin: float


class ShadowCalibrator:
    def __init__(self, path: Path | None, base_margin: float, step: float, max_margin: float) -> None:
        self.path = path
        self.base_margin = base_margin
        self.step = step
        self.max_margin = max_margin
        self._state: Dict[str, CalibrationState] = {}
        if self.path and self.path.exists():
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            for epoch_id, data in payload.get("epochs", {}).items():
                self._state[epoch_id] = CalibrationState(margin=float(data.get("margin", base_margin)))

    def margin_for_epoch(self, epoch_id: str) -> float:
        state = self._state.get(epoch_id)
        if state:
            return state.margin
        return self.base_margin

    def record_outcome(self, epoch_id: str, shadow_decision: str, promoted_result: str) -> None:
        if shadow_decision != "PASS" or promoted_result != "FAIL":
            return
        current = self.margin_for_epoch(epoch_id)
        updated = min(self.max_margin, current + self.step)
        self._state[epoch_id] = CalibrationState(margin=updated)
        self._save()

    def _save(self) -> None:
        if not self.path:
            return
        payload = {"epochs": {}}
        for epoch_id, state in self._state.items():
            payload["epochs"][epoch_id] = {"margin": state.margin}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
