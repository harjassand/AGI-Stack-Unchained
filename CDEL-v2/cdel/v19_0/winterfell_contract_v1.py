"""Helpers for pinned Winterfell backend/profile contract checks."""

from __future__ import annotations

from typing import Any, Iterable

from .common_v1 import canon_hash_obj

_PROFILE_META_FIELDS: tuple[str, ...] = (
    "winterfell_backend_id",
    "winterfell_backend_version",
    "winterfell_field_id",
    "winterfell_extension_id",
    "winterfell_merkle_hasher_id",
    "winterfell_random_coin_hasher_id",
)


def _require_text(value: Any, *, reason: str) -> str:
    if not isinstance(value, str):
        raise ValueError(reason)
    text = value.strip()
    if not text:
        raise ValueError(reason)
    return text


def _normalize_option_keys(value: Any, *, reason: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(reason)
    seen: set[str] = set()
    out: list[str] = []
    for row in value:
        key = _require_text(row, reason=reason)
        if key in seen:
            raise ValueError(reason)
        seen.add(key)
        out.append(key)
    return tuple(out)


def canonicalize_winterfell_proof_options(
    *,
    options_obj: Any,
    option_keys: Iterable[str],
    reason: str = "SCHEMA_FAIL",
) -> dict[str, Any]:
    if not isinstance(options_obj, dict):
        raise ValueError(reason)
    expected_keys = tuple(option_keys)
    expected = set(expected_keys)
    provided = set(str(key) for key in options_obj.keys())
    if provided != expected:
        raise ValueError(reason)
    return {key: options_obj[key] for key in expected_keys}


def resolve_profile_backend_contract_bindings(
    *,
    profile_payload: dict[str, Any],
    backend_contract_payload: dict[str, Any],
    reason: str = "SCHEMA_FAIL",
) -> dict[str, Any]:
    if not isinstance(profile_payload, dict) or not isinstance(backend_contract_payload, dict):
        raise ValueError(reason)
    contract_option_keys = _normalize_option_keys(
        backend_contract_payload.get("winterfell_proof_options_keys"),
        reason=reason,
    )
    contract_meta: dict[str, str] = {}
    for field in _PROFILE_META_FIELDS:
        contract_meta[field] = _require_text(backend_contract_payload.get(field), reason=reason)
        profile_value = _require_text(profile_payload.get(field), reason=reason)
        if profile_value != contract_meta[field]:
            raise ValueError(reason)
    canonical_options = canonicalize_winterfell_proof_options(
        options_obj=profile_payload.get("winterfell_proof_options"),
        option_keys=contract_option_keys,
        reason=reason,
    )
    return {
        **contract_meta,
        "winterfell_proof_options_keys": list(contract_option_keys),
        "winterfell_proof_options": canonical_options,
        "proof_options_hash": canon_hash_obj(canonical_options),
    }


__all__ = [
    "canonicalize_winterfell_proof_options",
    "resolve_profile_backend_contract_bindings",
]
