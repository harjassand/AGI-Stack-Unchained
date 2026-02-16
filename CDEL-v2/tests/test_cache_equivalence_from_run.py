import json
from pathlib import Path

import pytest

from tools.repro_cache_diff import _normalize_report


def test_cache_equivalence_from_run():
    case_path = Path("tools/repro_cache_case.json")
    if not case_path.exists():
        pytest.skip("missing repro_cache_case.json")
    case = json.loads(case_path.read_text(encoding="utf-8"))
    base = Path(case["baseline_run"]) / "report.json"
    cache = Path(case["cache_run"]) / "report.json"
    if not base.exists() or not cache.exists():
        pytest.skip("run artifacts not available")
    base_rows = _normalize_report(base)
    cache_rows = _normalize_report(cache)
    assert base_rows == cache_rows
