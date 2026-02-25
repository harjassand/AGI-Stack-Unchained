"""Deterministic AUTH_HASH helpers for CCAP authority pins v1."""

from __future__ import annotations

import re
import os
from pathlib import Path
from typing import Any

from ...v1_7r.canon import canon_bytes, sha256_prefixed
from ..omega_common_v1 import canon_hash_obj, fail, load_canon_dict


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
_OPTIONAL_V2_KEYS = {
    "anchor_suite_set_id",
    "active_kernel_extensions_ledger_id",
    "suite_runner_id",
    "holdout_policy_id",
    "holdout_store_root_id",
}
_OPTIONAL_STEP5_KEYS = {
    "orch_policy_eval_holdout_dataset_id",
    "orch_policy_eval_config_id",
}
_ALLOWED_KEYS = _REQUIRED_KEYS | _OPTIONAL_V2_KEYS | _OPTIONAL_STEP5_KEYS

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


def _repo_root_from_module() -> Path:
    return Path(__file__).resolve().parents[4]


def _step5_orch_policy_enabled(*, pins: dict[str, Any]) -> bool:
    raw = str(os.environ.get("OMEGA_STEP5_ORCH_POLICY_ENABLE_B", "0")).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    return bool(
        str(pins.get("orch_policy_eval_holdout_dataset_id", "")).strip()
        or str(pins.get("orch_policy_eval_config_id", "")).strip()
    )


def _active_ek_schema_version(*, pins: dict[str, Any], repo_root_path: Path) -> str:
    active_ek_id = _require_sha256(pins.get("active_ek_id"))
    kernels_dir = repo_root_path / "authority" / "evaluation_kernels"
    if not kernels_dir.exists() or not kernels_dir.is_dir():
        fail("SCHEMA_FAIL")
    for path in sorted(kernels_dir.glob("*.json"), key=lambda row: row.as_posix()):
        payload = load_canon_dict(path)
        schema_version = str(payload.get("schema_version", "")).strip()
        if schema_version not in {"evaluation_kernel_v1", "evaluation_kernel_v2"}:
            continue
        if canon_hash_obj(payload) == active_ek_id:
            return schema_version
    fail("SCHEMA_FAIL")
    return "evaluation_kernel_v1"


def _normalize_authority_pins(pins: dict[str, Any], *, repo_root_path: Path | None = None) -> dict[str, Any]:
    if not isinstance(pins, dict):
        fail("SCHEMA_FAIL")
    keys = set(pins.keys())
    if not _REQUIRED_KEYS.issubset(keys):
        fail("SCHEMA_FAIL")
    if not keys.issubset(_ALLOWED_KEYS):
        fail("SCHEMA_FAIL")
    if pins.get("schema_version") != "authority_pins_v1":
        fail("SCHEMA_FAIL")

    canon = pins.get("canon_version_ids")
    if not isinstance(canon, dict) or set(canon.keys()) != _CANON_KEYS:
        fail("SCHEMA_FAIL")

    normalized = {
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
    anchor_suite_set_id = pins.get("anchor_suite_set_id")
    if anchor_suite_set_id is not None:
        normalized["anchor_suite_set_id"] = _require_sha256(anchor_suite_set_id)
    active_kernel_extensions_ledger_id = pins.get("active_kernel_extensions_ledger_id")
    if active_kernel_extensions_ledger_id is not None:
        normalized["active_kernel_extensions_ledger_id"] = _require_sha256(active_kernel_extensions_ledger_id)
    suite_runner_id = pins.get("suite_runner_id")
    if suite_runner_id is not None:
        normalized["suite_runner_id"] = _require_sha256(suite_runner_id)
    holdout_policy_id = pins.get("holdout_policy_id")
    if holdout_policy_id is not None:
        normalized["holdout_policy_id"] = _require_sha256(holdout_policy_id)
    holdout_store_root_id = pins.get("holdout_store_root_id")
    if holdout_store_root_id is not None:
        normalized["holdout_store_root_id"] = _require_sha256(holdout_store_root_id)
    orch_policy_eval_holdout_dataset_id = pins.get("orch_policy_eval_holdout_dataset_id")
    if orch_policy_eval_holdout_dataset_id is not None:
        normalized["orch_policy_eval_holdout_dataset_id"] = _require_sha256(orch_policy_eval_holdout_dataset_id)
    orch_policy_eval_config_id = pins.get("orch_policy_eval_config_id")
    if orch_policy_eval_config_id is not None:
        normalized["orch_policy_eval_config_id"] = _require_sha256(orch_policy_eval_config_id)

    resolved_repo_root = Path(repo_root_path).resolve() if repo_root_path is not None else _repo_root_from_module()
    active_schema_version = _active_ek_schema_version(pins=normalized, repo_root_path=resolved_repo_root)
    if active_schema_version == "evaluation_kernel_v2":
        missing = [key for key in sorted(_OPTIONAL_V2_KEYS) if key not in normalized]
        if missing:
            fail("SCHEMA_FAIL")
    if _step5_orch_policy_enabled(pins=normalized):
        missing = [key for key in sorted(_OPTIONAL_STEP5_KEYS) if key not in normalized]
        if missing:
            fail("SCHEMA_FAIL")
    return normalized


def authority_pins_path(repo_root: Path) -> Path:
    override = str(os.environ.get("OMEGA_AUTHORITY_PINS_REL", "")).strip()
    if override:
        rel = override.replace("\\", "/").lstrip("./")
        path = Path(rel)
        if path.is_absolute() or ".." in path.parts:
            fail("SCHEMA_FAIL")
        return (Path(repo_root).resolve() / path).resolve()
    return Path(repo_root).resolve() / "authority" / "authority_pins_v1.json"


def load_authority_pins(repo_root: Path) -> dict[str, Any]:
    pins_path = authority_pins_path(repo_root)
    if not pins_path.exists() or not pins_path.is_file():
        fail("MISSING_STATE_INPUT")
    payload = load_canon_dict(pins_path)
    return _normalize_authority_pins(payload, repo_root_path=Path(repo_root).resolve())


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
