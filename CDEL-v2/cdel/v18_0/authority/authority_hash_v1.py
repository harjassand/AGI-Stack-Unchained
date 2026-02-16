"""Deterministic AUTH_HASH helpers for CCAP authority pins v1."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ...v1_7r.canon import canon_bytes, sha256_prefixed
from ..omega_common_v1 import fail, load_canon_dict


_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

_REQUIRED_KEYS = {
    "schema_version",
    "re1_constitution_state_id",
    "re2_verifier_state_id",
    "active_ek_id",
    "active_op_pool_ids",
    "active_dsbx_profile_ids",
    "env_contract_id",
    "toolchain_root_id",
    "ccap_patch_allowlists_id",
    "canon_version_ids",
}

_CANON_KEYS = {"ccap_can_v", "ir_can_v", "op_can_v", "obs_can_v"}


def _require_sha256(value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        fail("SCHEMA_FAIL")
    return value


def _require_sha256_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        fail("SCHEMA_FAIL")
    out: list[str] = []
    for row in value:
        out.append(_require_sha256(row))
    return out


def _normalize_authority_pins(pins: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(pins, dict):
        fail("SCHEMA_FAIL")
    if set(pins.keys()) != _REQUIRED_KEYS:
        fail("SCHEMA_FAIL")
    if pins.get("schema_version") != "authority_pins_v1":
        fail("SCHEMA_FAIL")

    canon = pins.get("canon_version_ids")
    if not isinstance(canon, dict) or set(canon.keys()) != _CANON_KEYS:
        fail("SCHEMA_FAIL")

    return {
        "schema_version": "authority_pins_v1",
        "re1_constitution_state_id": _require_sha256(pins.get("re1_constitution_state_id")),
        "re2_verifier_state_id": _require_sha256(pins.get("re2_verifier_state_id")),
        "active_ek_id": _require_sha256(pins.get("active_ek_id")),
        "active_op_pool_ids": _require_sha256_list(pins.get("active_op_pool_ids")),
        "active_dsbx_profile_ids": _require_sha256_list(pins.get("active_dsbx_profile_ids")),
        "env_contract_id": _require_sha256(pins.get("env_contract_id")),
        "toolchain_root_id": _require_sha256(pins.get("toolchain_root_id")),
        "ccap_patch_allowlists_id": _require_sha256(pins.get("ccap_patch_allowlists_id")),
        "canon_version_ids": {
            "ccap_can_v": _require_sha256(canon.get("ccap_can_v")),
            "ir_can_v": _require_sha256(canon.get("ir_can_v")),
            "op_can_v": _require_sha256(canon.get("op_can_v")),
            "obs_can_v": _require_sha256(canon.get("obs_can_v")),
        },
    }


def authority_pins_path(repo_root: Path) -> Path:
    return Path(repo_root).resolve() / "authority" / "authority_pins_v1.json"


def load_authority_pins(repo_root: Path) -> dict[str, Any]:
    pins_path = authority_pins_path(repo_root)
    if not pins_path.exists() or not pins_path.is_file():
        fail("MISSING_STATE_INPUT")
    payload = load_canon_dict(pins_path)
    return _normalize_authority_pins(payload)


def canon_authority(pins: dict[str, Any]) -> bytes:
    normalized = _normalize_authority_pins(pins)
    return canon_bytes(normalized)


def auth_hash(pins: dict[str, Any]) -> str:
    return sha256_prefixed(canon_authority(pins))


__all__ = [
    "authority_pins_path",
    "auth_hash",
    "canon_authority",
    "load_authority_pins",
]
