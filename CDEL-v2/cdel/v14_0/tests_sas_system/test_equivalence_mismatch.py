from __future__ import annotations

import sys
import types

import pytest

from cdel.v14_0.sas_system_equivalence_v1 import SASSystemEquivalenceError, run_equivalence


def test_equivalence_mismatch_constant_output() -> None:
    mod = types.ModuleType("fake_rust_mod")

    def compute(_job_bytes: bytes) -> bytes:
        return (
            b"{\"schema\":\"sas_science_workmeter_out_v1\",\"spec_version\":\"v14_0\","
            b"\"sqrt_calls\":0,\"div_calls\":0,\"pair_terms_evaluated\":0,\"work_cost_total\":0}"
        )

    mod.compute = compute  # type: ignore[attr-defined]
    sys.modules["fake_rust_mod"] = mod

    suite = {
        "schema_version": "sas_system_suitepack_v1",
        "suite_id": "test_suite",
        "cases": [
            {
                "case_id": "c1",
                "tier": "S",
                "job": {
                    "schema": "sas_science_workmeter_job_v1",
                    "spec_version": "v14_0",
                    "dim": 1,
                    "norm_pow": 2,
                    "pair_terms": 1,
                    "hooke_terms": 0,
                },
            }
        ],
    }

    with pytest.raises(SASSystemEquivalenceError) as exc:
        run_equivalence(suitepack=suite, rust_module="fake_rust_mod")
    assert "INVALID:OUTPUT_MISMATCH" in str(exc.value)
