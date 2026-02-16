from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "CDEL-v2") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "CDEL-v2"))


def _load_gate_matrix_module():
    module_path = REPO_ROOT / "tools" / "v19_smoke" / "run_gate_matrix_e2e.py"
    spec = importlib.util.spec_from_file_location("v19_gate_matrix_e2e_module", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"unable to load module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_v19_gate_matrix_e2e(tmp_path: Path) -> None:
    module = _load_gate_matrix_module()
    summary = module.run_gate_matrix(out_dir=tmp_path / "gate_matrix")
    assert summary["all_passed"] is True
