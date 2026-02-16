from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parent / "meta-core" / "tests_orchestration" / "test_v19_wiring_smoke.py"
    spec = importlib.util.spec_from_file_location("meta_core_v19_wiring_smoke", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"unable to load module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_v19_pack_registry_wiring_smoke() -> None:
    module = _load_module()
    module.test_v19_pack_registry_wiring_smoke()
