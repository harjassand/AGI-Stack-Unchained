from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import List


@dataclass
class Primitive:
    primitive_id: str
    operator_signature: str
    metric_target: float
    metric_direction: str
    provenance: list[str]


class Library:
    def __init__(self, primitives: List[Primitive]) -> None:
        self.primitives = primitives

    @classmethod
    def load(cls, path: Path) -> "Library":
        if not path.exists():
            return cls([])
        payload = json.loads(path.read_text(encoding="utf-8"))
        primitives = []
        for item in payload.get("primitives", []):
            primitives.append(
                Primitive(
                    primitive_id=item["primitive_id"],
                    operator_signature=item["operator_signature"],
                    metric_target=float(item["metric_target"]),
                    metric_direction=item.get("metric_direction", "maximize"),
                    provenance=list(item.get("provenance", [])),
                )
            )
        return cls(primitives)

    def save(self, path: Path) -> None:
        payload = {"primitives": []}
        for prim in self.primitives:
            payload["primitives"].append(
                {
                    "primitive_id": prim.primitive_id,
                    "operator_signature": prim.operator_signature,
                    "metric_target": prim.metric_target,
                    "metric_direction": prim.metric_direction,
                    "provenance": prim.provenance,
                }
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def has(self, primitive_id: str) -> bool:
        return any(prim.primitive_id == primitive_id for prim in self.primitives)

    def add(self, prim: Primitive) -> bool:
        if self.has(prim.primitive_id):
            return False
        self.primitives.append(prim)
        return True

    def select(self, rng) -> Primitive:
        if not self.primitives:
            raise ValueError("no primitives available")
        idx = rng.randrange(len(self.primitives))
        return self.primitives[idx]


def primitive_id(operator_signature: str, metric_direction: str) -> str:
    payload = f"{operator_signature}:{metric_direction}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
