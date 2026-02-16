from __future__ import annotations

import os

from cdel.v18_0.omega_activator_v1 import run_activation


def test_rollback_triggers_on_regression(tmp_path) -> None:
    state_root = tmp_path / "state"
    dispatch_dir = state_root / "dispatch" / "x1"
    dispatch_dir.mkdir(parents=True)

    dispatch_ctx = {"dispatch_dir": dispatch_dir}
    promotion_receipt = {
        "result": {"status": "PROMOTED", "reason_code": None},
        "active_manifest_hash_after": "sha256:" + "8" * 64,
    }
    suitepack = {
        "schema_version": "healthcheck_suitepack_v1",
        "checks": [
            {
                "check_id": "must_exist",
                "kind": "FILE_EXISTS",
                "target_rel": "missing/file.txt",
                "expected_hash": None,
                "required": True,
            }
        ],
    }

    prev_mode = os.environ.get("OMEGA_META_CORE_ACTIVATION_MODE")
    prev_allow = os.environ.get("OMEGA_ALLOW_SIMULATE_ACTIVATION")
    os.environ["OMEGA_META_CORE_ACTIVATION_MODE"] = "simulate"
    os.environ["OMEGA_ALLOW_SIMULATE_ACTIVATION"] = "1"
    try:
        activation, _, rollback, _, final_active = run_activation(
            tick_u64=1,
            dispatch_ctx=dispatch_ctx,
            promotion_receipt=promotion_receipt,
            healthcheck_suitepack=suitepack,
            healthcheck_suite_hash="sha256:" + "7" * 64,
            active_manifest_hash_before="sha256:" + "1" * 64,
        )
    finally:
        if prev_mode is None:
            os.environ.pop("OMEGA_META_CORE_ACTIVATION_MODE", None)
        else:
            os.environ["OMEGA_META_CORE_ACTIVATION_MODE"] = prev_mode
        if prev_allow is None:
            os.environ.pop("OMEGA_ALLOW_SIMULATE_ACTIVATION", None)
        else:
            os.environ["OMEGA_ALLOW_SIMULATE_ACTIVATION"] = prev_allow

    assert activation is not None
    assert activation["healthcheck_result"] == "FAIL"
    assert rollback is not None
    assert rollback["cause"] == "HEALTHCHECK_FAIL"
    assert final_active == "sha256:" + "1" * 64
