"""Pinned ICAN canonicalization profile for overlap-kernel portability."""

from __future__ import annotations

import hashlib
from typing import Any

from ..common_v1 import canon_hash_obj, ensure_sha256, fail, validate_schema, verify_object_id
from ...v1_7r.canon import canon_bytes


def _reject_cr_strings(value: Any) -> None:
    if isinstance(value, dict):
        for row in value.values():
            _reject_cr_strings(row)
        return
    if isinstance(value, list):
        for row in value:
            _reject_cr_strings(row)
        return
    if isinstance(value, str) and "\r" in value:
        fail("SCHEMA_FAIL")


def profile_id_from_profile(profile: dict[str, Any]) -> str:
    payload = dict(profile)
    payload.pop("profile_id", None)
    return canon_hash_obj(payload)


def build_default_ican_profile() -> dict[str, Any]:
    profile = {
        "schema_name": "ok_canonicalization_profile_v1",
        "schema_version": "v19_0",
        "encoding": "UTF-8",
        "sort_keys": "LEXICOGRAPHIC",
        "separators": "COMPACT_JSON",
        "allow_floats": False,
        "allowed_json_types": ["object", "array", "string", "integer", "boolean", "null"],
        "newline_policy": "LF_ONLY_REJECT_CR",
        "v1_7r_equivalent": True,
    }
    profile["profile_id"] = profile_id_from_profile(profile)
    validate_schema(profile, "ok_canonicalization_profile_v1")
    verify_object_id(profile, id_field="profile_id")
    return profile


DEFAULT_ICAN_PROFILE = build_default_ican_profile()


def _resolve_profile(*, profile_id: str, profile: dict[str, Any] | None) -> dict[str, Any]:
    expected = ensure_sha256(profile_id, reason="SCHEMA_FAIL")
    if profile is None:
        if expected != DEFAULT_ICAN_PROFILE["profile_id"]:
            fail("SAFE_HALT:UNKNOWN_ICAN_PROFILE")
        return dict(DEFAULT_ICAN_PROFILE)

    validate_schema(profile, "ok_canonicalization_profile_v1")
    observed = verify_object_id(profile, id_field="profile_id")
    if observed != expected:
        fail("SAFE_HALT:UNKNOWN_ICAN_PROFILE")
    return dict(profile)


def ican_canon(obj: Any, profile_id: str, profile: dict[str, Any] | None = None) -> bytes:
    resolved = _resolve_profile(profile_id=profile_id, profile=profile)
    if resolved.get("newline_policy") != "LF_ONLY_REJECT_CR":
        fail("SCHEMA_FAIL")
    _reject_cr_strings(obj)
    return canon_bytes(obj)


def ican_id(obj: Any, profile_id: str, profile: dict[str, Any] | None = None) -> str:
    return "sha256:" + hashlib.sha256(ican_canon(obj, profile_id, profile)).hexdigest()


__all__ = [
    "DEFAULT_ICAN_PROFILE",
    "build_default_ican_profile",
    "ican_canon",
    "ican_id",
    "profile_id_from_profile",
]
