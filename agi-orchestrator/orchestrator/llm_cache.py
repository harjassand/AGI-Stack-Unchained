"""Prompt/response cache for LLM backends."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from blake3 import blake3


@dataclass
class PromptCache:
    root: Path

    def _path_for_prompt(self, prompt: str) -> Path:
        digest = blake3(prompt.encode("utf-8")).hexdigest()
        return self.root / f"{digest}.json"

    def get(self, prompt: str) -> str | None:
        path = self._path_for_prompt(prompt)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        response = payload.get("response")
        return response if isinstance(response, str) else None

    def set(self, prompt: str, response: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path_for_prompt(prompt)
        payload = {"prompt": prompt, "response": response}
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
