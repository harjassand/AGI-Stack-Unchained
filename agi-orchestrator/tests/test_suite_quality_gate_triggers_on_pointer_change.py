from __future__ import annotations

import pytest

from scripts.check_suite_quality_gate import gate_quality


def test_suite_quality_gate_triggers_on_pointer_change() -> None:
    base_rows = [
        {"tests": [{"expected": 0}]},
        {"tests": [{"expected": 0}]},
    ]
    head_rows = [
        {"tests": [{"expected": 1}]},
        {"tests": [{"expected": 2}]},
    ]

    with pytest.raises(ValueError, match="baseline pass rate drift"):
        gate_quality(
            base_rows=base_rows,
            head_rows=head_rows,
            allowed_delta=0.1,
            min_size_delta=0,
            max_timeout_frac=0.5,
            max_security_frac=0.5,
        )
