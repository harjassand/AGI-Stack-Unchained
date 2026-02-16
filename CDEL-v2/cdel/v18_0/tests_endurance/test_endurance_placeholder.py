from __future__ import annotations

import pytest


@pytest.mark.skip(reason="endurance tier is scheduled separately")
def test_endurance_placeholder() -> None:
    assert True
