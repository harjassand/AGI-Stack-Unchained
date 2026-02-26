from __future__ import annotations

import hashlib
import json
from typing import Any

from cdel.v1_7r.canon import canon_bytes
from cdel.v18_0.omega_common_v1 import validate_schema as validate_schema_v18

_FORBIDDEN_TOKEN_SNIPPETS: tuple[str, ...] = (
    "<|im_start|>",
    "<|im_end|>",
    "\x00",
)


def _sha256_prefixed(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _ir_id_from_obj(obj: dict[str, Any]) -> str:
    no_id = dict(obj)
    no_id.pop("ir_id", None)
    return _sha256_prefixed(canon_bytes(no_id))


def build_task_prompt_v1(*, tick_u64: int, producer_run_id: str, candidate_index_u64: int) -> str:
    return (
        "Generate one strict JSON object that validates against polymath_restricted_ir_v1.\n"
        "Rules: numeric_mode must be Q32_FIXEDPOINT, operations must be non-empty, no markdown.\n"
        f"tick_u64={int(tick_u64)} producer_run_id={producer_run_id} candidate_index_u64={int(candidate_index_u64)}"
    )


def deterministic_ir_from_seed(*, seed_u64: int, candidate_index_u64: int, producer_run_id: str) -> dict[str, Any]:
    seed = int(seed_u64) & ((1 << 64) - 1)
    op_id = f"ttc_grpo_op_{seed:016x}_{int(candidate_index_u64)}"
    sip_hash = _sha256_prefixed(f"sip|{producer_run_id}|{seed}".encode("utf-8"))
    kernel_hash = _sha256_prefixed(f"kernel|{producer_run_id}|{seed}".encode("utf-8"))
    const_a = int(seed & 0x7FFFFFFF)
    const_b = int((seed >> 1) & 0x7FFFFFFF)

    payload = {
        "schema_version": "polymath_restricted_ir_v1",
        "ir_id": "sha256:" + ("0" * 64),
        "op_id": op_id,
        "sip_knowledge_artifact_hash": sip_hash,
        "kernel_spec_hash": kernel_hash,
        "numeric_mode": "Q32_FIXEDPOINT",
        "entrypoint": {
            "name": "main",
            "args": ["x_q32", "y_q32"],
            "returns": "z_q32",
        },
        "constants_q32": [
            {"name": "K0", "value_i64": const_a},
            {"name": "K1", "value_i64": const_b},
        ],
        "operations": [
            {"op": "ADD_Q32", "args": [0, 1]},
            {"op": "MUL_Q32", "args": [0, 1]},
            {"op": "CLAMP_Q32", "args": [-(1 << 31), (1 << 31) - 1]},
        ],
    }
    payload["ir_id"] = _ir_id_from_obj(payload)
    return payload


def _extract_json_object_text(text: str) -> str | None:
    stripped = str(text).strip()
    if not stripped:
        return None
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    fence = "```"
    if fence in stripped:
        parts = [row for row in stripped.split(fence) if row.strip()]
        for part in parts:
            candidate = part.strip()
            if candidate.startswith("json"):
                candidate = candidate[4:].strip()
            if candidate.startswith("{") and candidate.endswith("}"):
                return candidate

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        return stripped[start : end + 1]
    return None


def parse_polymath_restricted_ir_v1(text: str) -> tuple[dict[str, Any] | None, str | None]:
    raw = str(text)
    for token in _FORBIDDEN_TOKEN_SNIPPETS:
        if token in raw:
            return None, f"FORBIDDEN_TOKEN:{token}"

    json_blob = _extract_json_object_text(raw)
    if json_blob is None:
        return None, "PARSE_FAIL:NO_JSON_OBJECT"

    try:
        payload = json.loads(json_blob)
    except Exception as exc:  # noqa: BLE001
        return None, f"PARSE_FAIL:JSON_DECODE:{exc.__class__.__name__}"

    if not isinstance(payload, dict):
        return None, "PARSE_FAIL:NOT_OBJECT"

    declared_ir_id = str(payload.get("ir_id", "")).strip()
    expected_ir_id = _ir_id_from_obj(payload)
    if declared_ir_id and declared_ir_id != expected_ir_id:
        return None, "ID_MISMATCH"
    payload["ir_id"] = expected_ir_id

    try:
        validate_schema_v18(payload, "polymath_restricted_ir_v1")
    except Exception as exc:  # noqa: BLE001
        return None, f"SCHEMA_FAIL:{exc.__class__.__name__}"

    return payload, None


__all__ = [
    "build_task_prompt_v1",
    "deterministic_ir_from_seed",
    "parse_polymath_restricted_ir_v1",
]
