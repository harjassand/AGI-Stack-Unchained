from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_ladder_module():
    module_path = Path(__file__).resolve().parent / "tools" / "v19_hypothesis" / "run_ladder.py"
    spec = importlib.util.spec_from_file_location("v19_ladder_harness_module", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"unable to load ladder module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_v19_ladder_harness(tmp_path: Path) -> None:
    module = _load_ladder_module()
    summary = module.run_ladder(out_dir=tmp_path / "ladder")
    assert bool(summary.get("all_passed", False))
    rows = summary.get("rows")
    assert isinstance(rows, list) and rows
    for row in rows:
        assert str(row.get("positive_outcome")) == "ACCEPT"
        assert str(row.get("negative_outcome")) in {"SAFE_HALT", "SAFE_SPLIT"}
