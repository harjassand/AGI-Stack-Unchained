from __future__ import annotations

import pytest

from cdel.v18_0.omega_common_v1 import OmegaV18Error
from cdel.v19_0.verify_kernel_extension_proposal_v1 import _phase1_public_only_guard


def test_extension_proposal_public_only_guardrail_v1() -> None:
    ext_spec = {
        "schema_version": "kernel_extension_spec_v1",
        "extension_spec_id": "sha256:" + ("1" * 64),
        "anchor_ek_id": "sha256:" + ("2" * 64),
        "extension_name": "apa_hidden_ext",
        "suite_set_id": "sha256:" + ("3" * 64),
        "suite_set_relpath": "benchmark_suite_set_v1.json",
        "additive_only_b": True,
    }
    suite_manifest = {
        "schema_version": "benchmark_suite_manifest_v1",
        "suite_id": "sha256:" + ("4" * 64),
        "suite_name": "private_hidden_suite",
        "suite_runner_relpath": "tools/omega/omega_benchmark_suite_composite_v1.py",
        "visibility": "HIDDEN",
        "labels": ["internal"],
        "metrics": {"q32_metric_ids": ["accuracy_q32"], "public_only_b": False},
    }
    suite_set = {
        "schema_version": "benchmark_suite_set_v1",
        "suite_set_id": "sha256:" + ("3" * 64),
        "suite_set_kind": "EXTENSION",
        "anchor_ek_id": "sha256:" + ("2" * 64),
        "suites": [
            {
                "suite_id": "sha256:" + ("4" * 64),
                "suite_manifest_id": "sha256:" + ("4" * 64),
                "suite_manifest_relpath": "benchmark_suite_manifest_v1.json",
                "ordinal_u64": 0,
            }
        ],
    }

    with pytest.raises(OmegaV18Error) as exc:
        _phase1_public_only_guard(ext_spec, suite_manifest, suite_set)
    assert "PHASE1_PUBLIC_ONLY_VIOLATION" in str(exc.value)
