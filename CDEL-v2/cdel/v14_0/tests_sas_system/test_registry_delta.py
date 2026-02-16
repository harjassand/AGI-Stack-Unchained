from __future__ import annotations

import pytest

from cdel.v14_0.verify_rsi_sas_system_v1 import SASSystemError, _validate_registry_delta


def test_registry_delta_rejects_new_component() -> None:
    before = {
        "schema": "sas_system_component_registry_v1",
        "spec_version": "v14_0",
        "components": {"SAS_SCIENCE_WORKMETER_V1": {"active_backend": "PY_REF_V1", "rust_ext": None}},
    }
    after = {
        "schema": "sas_system_component_registry_v1",
        "spec_version": "v14_0",
        "components": {
            "SAS_SCIENCE_WORKMETER_V1": {"active_backend": "PY_REF_V1", "rust_ext": None},
            "NEW_COMPONENT": {"active_backend": "PY_REF_V1", "rust_ext": None},
        },
    }
    with pytest.raises(SASSystemError) as exc:
        _validate_registry_delta(before, after)
    assert "INVALID:REGISTRY_FORBIDDEN_EDIT" in str(exc.value)


def test_registry_delta_rejects_unknown_component_catalog() -> None:
    before = {
        "schema": "sas_system_component_registry_v1",
        "spec_version": "v14_0",
        "components": {"OTHER_COMPONENT": {"active_backend": "PY_REF_V1", "rust_ext": None}},
    }
    after = {
        "schema": "sas_system_component_registry_v1",
        "spec_version": "v14_0",
        "components": {"OTHER_COMPONENT": {"active_backend": "PY_REF_V1", "rust_ext": None}},
    }
    with pytest.raises(SASSystemError) as exc:
        _validate_registry_delta(before, after)
    assert "INVALID:REGISTRY_UNKNOWN_COMPONENT" in str(exc.value)


def test_registry_delta_rejects_unrelated_edit() -> None:
    before = {
        "schema": "sas_system_component_registry_v1",
        "spec_version": "v14_0",
        "components": {"SAS_SCIENCE_WORKMETER_V1": {"active_backend": "PY_REF_V1", "rust_ext": None}},
    }
    after = {
        "schema": "sas_system_component_registry_v1",
        "spec_version": "v14_0",
        "components": {"SAS_SCIENCE_WORKMETER_V1": {"active_backend": "PY_REF_V1", "rust_ext": None, "extra": 1}},
    }
    with pytest.raises(SASSystemError) as exc:
        _validate_registry_delta(before, after)
    assert "INVALID:REGISTRY_FORBIDDEN_EDIT" in str(exc.value)
