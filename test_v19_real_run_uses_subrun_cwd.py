from __future__ import annotations

from pathlib import Path

import pytest

from test_v19_promotion_cwd_subrun_required import test_v19_promotion_requires_subrun_cwd


def test_v19_real_run_uses_subrun_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Alias regression: coordinator promotion/subverifier must run from the subrun CWD."""

    test_v19_promotion_requires_subrun_cwd(tmp_path, monkeypatch)

