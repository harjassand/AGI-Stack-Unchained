from __future__ import annotations

import json
from pathlib import Path

from tools.omega.agi_micdrop_solver_v1 import solve_prompt


def test_solver_matches_public_micdrop_devset_v2(monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    devset_path = repo_root / "tools" / "omega" / "micdrop_devset_v2.json"
    payload = json.loads(devset_path.read_text(encoding="utf-8"))
    rows = list(payload.get("rows") or [])
    assert rows, "devset rows missing"

    monkeypatch.setenv("MICDROP_CAPABILITY_LEVEL_OVERRIDE", "4")
    for row in rows:
        prompt = str(row.get("prompt", ""))
        expected = str(row.get("label", ""))
        meta = row.get("meta")
        prediction = solve_prompt(prompt, meta if isinstance(meta, dict) else None)
        assert prediction == expected, f"id={row.get('id')}"
