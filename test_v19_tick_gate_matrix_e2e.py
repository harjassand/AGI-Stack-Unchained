from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
_ORDERED_PATHS = [str(REPO_ROOT / "CDEL-v2"), str(REPO_ROOT)]
for _path in _ORDERED_PATHS:
    while _path in sys.path:
        sys.path.remove(_path)
for _path in reversed(_ORDERED_PATHS):
    sys.path.insert(0, _path)


def _load_tick_gate_matrix_module():
    module_path = REPO_ROOT / "tools" / "v19_smoke" / "run_tick_gate_matrix_e2e.py"
    spec = importlib.util.spec_from_file_location("v19_tick_gate_matrix_e2e_module", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"unable to load module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_v19_tick_gate_matrix_e2e(tmp_path: Path) -> None:
    module = _load_tick_gate_matrix_module()
    summary = module.run_tick_gate_matrix(out_dir=tmp_path / "tick_gate_matrix")
    assert summary["all_passed"] is True
