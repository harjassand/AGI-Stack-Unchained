from __future__ import annotations

import importlib.util
from pathlib import Path


def test_preflight_imports() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "preflight.py"
    spec = importlib.util.spec_from_file_location("preflight", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    missing = module.check_imports()
    assert missing == []
