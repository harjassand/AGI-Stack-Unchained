from __future__ import annotations

from cdel.v18_0.omega_executor_v1 import _prune_subrun_root


def _write(path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_subrun_prune_removes_known_junk(tmp_path) -> None:
    subrun_root = tmp_path / "subrun"
    _write(subrun_root / "module" / "__pycache__" / "a.pyc")
    _write(subrun_root / "tests" / ".pytest_cache" / "v" / "cache")
    _write(subrun_root / ".mypy_cache" / "meta.json")
    _write(subrun_root / ".ruff_cache" / "cache.db")
    _write(subrun_root / "nested" / ".DS_Store")
    _write(subrun_root / "keep" / "artifact.json", "{}")

    _prune_subrun_root(subrun_root_abs=subrun_root, campaign_id="rsi_sas_code_v12_0")

    assert not any(subrun_root.rglob("__pycache__"))
    assert not any(subrun_root.rglob(".pytest_cache"))
    assert not any(subrun_root.rglob(".mypy_cache"))
    assert not any(subrun_root.rglob(".ruff_cache"))
    assert not any(subrun_root.rglob(".DS_Store"))
    assert (subrun_root / "keep" / "artifact.json").exists()
