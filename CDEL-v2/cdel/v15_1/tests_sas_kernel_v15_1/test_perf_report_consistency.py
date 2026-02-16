from __future__ import annotations

import pytest

from cdel.v15_1.verify_rsi_sas_kernel_v15_1 import V15_1KernelError, _enforce_kernel_perf_integrity


def _base_report() -> dict[str, object]:
    return {
        "schema_version": "kernel_brain_perf_report_v1",
        "baseline_brain_opcodes_total": 500,
        "candidate_brain_opcodes_total": 5,
        "gate_multiplier": 1000,
        "gate_pass": True,
        "per_case": [
            {
                "case_id": "sha256:" + ("1" * 64),
                "baseline_opcodes": 250,
                "candidate_opcodes": 2,
            },
            {
                "case_id": "sha256:" + ("2" * 64),
                "baseline_opcodes": 250,
                "candidate_opcodes": 3,
            },
        ],
    }


def test_perf_report_consistency() -> None:
    report = _base_report()
    _enforce_kernel_perf_integrity(perf_report=report, expected_cases=2)


def test_perf_report_inconsistent_case_count() -> None:
    report = _base_report()
    with pytest.raises(V15_1KernelError):
        _enforce_kernel_perf_integrity(perf_report=report, expected_cases=3)


def test_perf_report_inconsistent_totals() -> None:
    report = _base_report()
    report["candidate_brain_opcodes_total"] = 6
    with pytest.raises(V15_1KernelError):
        _enforce_kernel_perf_integrity(perf_report=report, expected_cases=2)
