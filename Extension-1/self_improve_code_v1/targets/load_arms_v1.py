"""Arm loader and validator (v1)."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from ..canon.json_canon_v1 import canon_bytes
from ..canon.hash_v1 import sha256_hex

ALLOWED_OPS = {
    "set_int_literal_v1",
    "set_bool_literal_v1",
    "set_string_enum_v1",
    "set_small_int_table_v1",
    "set_weight_vector_v1",
}


def _normalize_value_set(value_set: List[Any]) -> List[str]:
    out: List[str] = []
    for v in value_set:
        if isinstance(v, bool):
            out.append("true" if v else "false")
        elif isinstance(v, int):
            out.append(str(v))
        elif isinstance(v, str):
            out.append(v)
        else:
            raise ValueError(f"unsupported value_set entry type: {type(v).__name__}")
    if not out:
        raise ValueError("value_set must be non-empty")
    return out


def compute_arm_id(arm: Dict[str, Any]) -> str:
    arm_body = dict(arm)
    arm_body.pop("arm_id", None)
    return sha256_hex(canon_bytes(arm_body))


def _validate_selector(selector: Dict[str, Any]) -> None:
    if "regex_single_match" in selector:
        if len(selector.keys()) != 1:
            raise ValueError("regex_single_match selector must be sole key")
        if not isinstance(selector["regex_single_match"], str):
            raise ValueError("regex_single_match must be string")
        return
    if "anchor_before" in selector and "anchor_after" in selector:
        if not isinstance(selector["anchor_before"], str) or not isinstance(selector["anchor_after"], str):
            raise ValueError("anchor selectors must be strings")
        if "occurrence" in selector and not isinstance(selector["occurrence"], int):
            raise ValueError("occurrence must be int")
        return
    raise ValueError("selector must have anchor_before/anchor_after or regex_single_match")


def _validate_relpath(path: str) -> None:
    if path.startswith("/") or ".." in path.split("/"):
        raise ValueError(f"invalid file_relpath: {path}")


def load_arms(path: str) -> List[Dict[str, Any]]:
    with open(path, "rb") as f:
        data = json.loads(f.read().decode("utf-8"))
    arms = data.get("arms") if isinstance(data, dict) else data
    if arms is None:
        raise ValueError("arms_v1 must be list or dict with 'arms'")
    if not isinstance(arms, list):
        raise ValueError("arms list missing")

    normalized: List[Dict[str, Any]] = []
    for arm in arms:
        if not isinstance(arm, dict):
            raise ValueError("arm must be dict")
        op_type = arm.get("op_type")
        if op_type not in ALLOWED_OPS:
            raise ValueError(f"invalid op_type: {op_type}")
        file_relpath = arm.get("file_relpath")
        if not isinstance(file_relpath, str):
            raise ValueError("file_relpath must be string")
        _validate_relpath(file_relpath)
        selector = arm.get("selector")
        if not isinstance(selector, dict):
            raise ValueError("selector must be dict")
        _validate_selector(selector)
        value_set = arm.get("value_set")
        if not isinstance(value_set, list):
            raise ValueError("value_set must be list")
        constraints = arm.get("constraints", {})
        if not isinstance(constraints, dict):
            raise ValueError("constraints must be dict")

        arm_id = arm.get("arm_id")
        if not isinstance(arm_id, str):
            raise ValueError("arm_id missing or not string")
        computed = compute_arm_id(arm)
        if arm_id != computed:
            raise ValueError(f"arm_id mismatch for {file_relpath}")

        normalized_arm = dict(arm)
        normalized_arm["value_set"] = _normalize_value_set(value_set)
        normalized.append(normalized_arm)

    return normalized


__all__ = ["load_arms", "compute_arm_id", "ALLOWED_OPS"]
