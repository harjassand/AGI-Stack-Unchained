"""Lease handling for SAS-MATH (v11.0)."""

from __future__ import annotations

from typing import Any

from cdel.v1_7r.canon import CanonError, load_canon_json


class LeaseError(CanonError):
    pass


def _fail(reason: str) -> None:
    raise LeaseError(reason)


def load_lease(path) -> dict[str, Any]:
    lease = load_canon_json(path)
    if not isinstance(lease, dict) or lease.get("schema_version") != "sas_math_lease_token_v1":
        _fail("SAS_MATH_LEASE_INVALID")
    for key in ["lease_id", "allowed_ops", "valid_from_tick", "valid_until_tick", "max_runs"]:
        if key not in lease:
            _fail("SAS_MATH_LEASE_INVALID")
    return lease


def validate_lease(lease: dict[str, Any], *, tick: int) -> None:
    allowed = lease.get("allowed_ops") or []
    required = {"SAS_MATH_DEV_EVAL", "SAS_MATH_HELDOUT_EVAL", "SAS_MATH_PROMOTE"}
    if not required.issubset(set(allowed)):
        _fail("SAS_MATH_LEASE_INVALID")
    valid_from = int(lease.get("valid_from_tick", 0))
    valid_until = int(lease.get("valid_until_tick", 0))
    if tick < valid_from or tick > valid_until:
        _fail("SAS_MATH_LEASE_INVALID")
    if int(lease.get("max_runs", 0)) < 1:
        _fail("SAS_MATH_LEASE_INVALID")


__all__ = ["load_lease", "validate_lease", "LeaseError"]
