from __future__ import annotations

from cli.caoe_proposer_cli_v1 import _regression_guard_failure


def test_regression_guard_blocks_base_success_drop() -> None:
    base = {"render_hold_01": 1.0}
    candidate = {"render_hold_01": 0.0}
    assert _regression_guard_failure(base, candidate) is True


def test_regression_guard_allows_no_drop() -> None:
    base = {"render_hold_01": 1.0}
    candidate = {"render_hold_01": 1.0}
    assert _regression_guard_failure(base, candidate) is False
