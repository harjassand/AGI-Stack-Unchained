from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Optional


@dataclass
class EnvHandle:
    env_id: str
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


class PolicyEnvRegistry:
    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self.base_dir = config_path.parent.parent
        self._config = _load_config(config_path)

    def resolve(self, env_id: str) -> Optional[EnvHandle]:
        envs = self._config.get("envs", {})
        spec = envs.get(env_id)
        if spec is None:
            return None
        rel_path = Path(spec.get("path", ""))
        resolved = _resolve_path(self.base_dir / rel_path, self.base_dir)
        if resolved is None or not resolved.exists():
            return None
        return EnvHandle(
            env_id=env_id,
            path=resolved,
            format=str(spec.get("format", "jsonl")),
        )
