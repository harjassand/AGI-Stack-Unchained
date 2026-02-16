from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from genesis.capsules.canonicalize import capsule_hash


class ComponentStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.components_dir = root / "components"

    def path_for_hash(self, capsule_hash_value: str) -> Path:
        return self.components_dir / f"{capsule_hash_value}.json"

    def has(self, capsule_hash_value: str) -> bool:
        return self.path_for_hash(capsule_hash_value).exists()

    def store(self, capsule: Dict) -> str:
        digest = capsule_hash(capsule)
        self.components_dir.mkdir(parents=True, exist_ok=True)
        path = self.path_for_hash(digest)
        path.write_text(json.dumps(capsule, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        return digest
