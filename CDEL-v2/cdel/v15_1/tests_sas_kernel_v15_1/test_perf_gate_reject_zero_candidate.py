from __future__ import annotations

import pytest

from cdel.v15_1.verify_rsi_sas_kernel_v15_1 import V15_1KernelError, _enforce_kernel_perf_integrity


def test_perf_gate_reject_zero_candidate() -> None:
    report = {
        "schema_version": "kernel_brain_perf_report_v1",
        "baseline_brain_opcodes_total": 100,
        "candidate_brain_opcodes_total": 0,
        "gate_multiplier": 1000,
        "gate_pass": True,
        "per_case": [
            {
                "case_id": "sha256:" + ("a" * 64),
                "baseline_opcodes": 100,
                "candidate_opcodes": 0,
            }
        ],
    }
    with pytest.raises(V15_1KernelError):
        _enforce_kernel_perf_integrity(perf_report=report, expected_cases=1)
