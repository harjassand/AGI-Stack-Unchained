from __future__ import annotations

from pathlib import Path


def test_capstone_includes_env_hard_metrics() -> None:
    script = Path("scripts") / "capstone_ae_validation.sh"
    content = script.read_text(encoding="utf-8")
    assert "\"env_hard\"" in content
    assert "baseline_success_rate" in content
    assert "library_success_rate" in content
