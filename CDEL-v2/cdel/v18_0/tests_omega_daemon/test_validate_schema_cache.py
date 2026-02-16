from __future__ import annotations

import pytest

from cdel.v18_0 import omega_common_v1 as omega_common


def test_validate_schema_reuses_cached_validator(monkeypatch) -> None:
    if omega_common.Draft202012Validator is None:
        pytest.skip("jsonschema unavailable")

    omega_common.SCHEMA_STORE_CACHE.clear()
    omega_common.VALIDATOR_CACHE.clear()

    real_validator_cls = omega_common.Draft202012Validator
    build_count = {"count": 0}

    def _validator_factory(*args, **kwargs):
        build_count["count"] += 1
        return real_validator_cls(*args, **kwargs)

    monkeypatch.setattr(omega_common, "Draft202012Validator", _validator_factory)

    payload = omega_common.load_canon_dict(
        omega_common.repo_root() / "campaigns" / "rsi_omega_daemon_v18_0" / "omega_policy_ir_v1.json"
    )
    omega_common.validate_schema(payload, "omega_policy_ir_v1")
    omega_common.validate_schema(payload, "omega_policy_ir_v1")

    assert build_count["count"] == 1
    assert len(omega_common.SCHEMA_STORE_CACHE) == 1
    assert len(omega_common.VALIDATOR_CACHE) == 1


def test_validate_schema_cache_preserves_validation_failures() -> None:
    omega_common.SCHEMA_STORE_CACHE.clear()
    omega_common.VALIDATOR_CACHE.clear()

    with pytest.raises(Exception):
        omega_common.validate_schema({}, "omega_policy_ir_v1")
