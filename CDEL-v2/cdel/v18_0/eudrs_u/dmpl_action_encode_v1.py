"""DMPL deterministic action records + encoding (v1).

Phase 2 contract:
  - Action records are stored as GCJ-1 canonical JSON artifacts (`dmpl_action_v1`).
  - aHash = sha256(canon_json(action_record)).
  - ActEncDet: deterministic Q32^p encoding from aHash32.
"""

from __future__ import annotations

import struct
from typing import Any

from .dmpl_types_v1 import (
    DMPLError,
    DMPL_E_HASH_MISMATCH,
    DMPL_E_OPSET_MISMATCH,
    I64_MAX,
    I64_MIN,
    _i64_le,
    _sha25632_count,
    _sha256_id_from_hex_digest32,
)
from .eudrs_u_hash_v1 import gcj1_canon_bytes

_ACTENC_PREFIX = b"DMPL/ACTENC/v1\x00"


def _require_u32(value: Any, *, reason: str) -> int:
    if not isinstance(value, int) or value < 0 or value > 0xFFFFFFFF:
        raise DMPLError(reason_code=reason, details={"value": value})
    return int(value)


def _require_i64(value: Any, *, reason: str) -> int:
    if not isinstance(value, int) or value < int(I64_MIN) or value > int(I64_MAX):
        raise DMPLError(reason_code=reason, details={"value": value})
    return int(value)


def make_noop_action_v1(dc1_id: str, opset_id: str) -> dict:
    return {
        "schema_id": "dmpl_action_v1",
        "dc1_id": str(dc1_id),
        "opset_id": str(opset_id),
        "kind": "NOOP",
        "opcode_u16": 0,
        "imm_i64": [],
        "ref_ids": [],
        "flags_u32": 0,
    }


def make_use_concept_action_v1(dc1_id: str, opset_id: str, i: int, concept_shard_id: str, ladder_level_u32: int) -> dict:
    return {
        "schema_id": "dmpl_action_v1",
        "dc1_id": str(dc1_id),
        "opset_id": str(opset_id),
        "kind": "USE_CONCEPT",
        "opcode_u16": 1,
        "imm_i64": [int(i)],
        "ref_ids": [str(concept_shard_id)],
        "flags_u32": int(ladder_level_u32),
    }


def _require_action_record_v1(action_obj: dict) -> dict[str, Any]:
    if not isinstance(action_obj, dict):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "action not dict"})
    expected_keys = {"schema_id", "dc1_id", "opset_id", "kind", "opcode_u16", "imm_i64", "ref_ids", "flags_u32"}
    if set(action_obj.keys()) != expected_keys:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "action keys"})
    if str(action_obj.get("schema_id", "")).strip() != "dmpl_action_v1":
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "schema_id"})
    kind = str(action_obj.get("kind", "")).strip()
    opcode_u16 = _require_u32(action_obj.get("opcode_u16"), reason=DMPL_E_OPSET_MISMATCH)
    if opcode_u16 > 0xFFFF:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "opcode range"})

    imm = action_obj.get("imm_i64")
    if not isinstance(imm, list):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "imm_i64 type"})
    imm_out = [_require_i64(v, reason=DMPL_E_OPSET_MISMATCH) for v in imm]

    ref_ids = action_obj.get("ref_ids")
    if not isinstance(ref_ids, list):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "ref_ids type"})
    ref_out: list[str] = []
    prev: str | None = None
    for rid in ref_ids:
        if not isinstance(rid, str):
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "ref_id type"})
        s = str(rid)
        if prev is not None and s < prev:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "ref_ids not sorted"})
        prev = s
        ref_out.append(s)

    flags_u32 = _require_u32(action_obj.get("flags_u32"), reason=DMPL_E_OPSET_MISMATCH)

    if kind == "NOOP":
        if opcode_u16 != 0 or imm_out or ref_out or flags_u32 != 0:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "bad NOOP"})
    elif kind == "USE_CONCEPT":
        if opcode_u16 != 1:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "bad USE_CONCEPT opcode"})
        if len(imm_out) != 1:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "USE_CONCEPT imm"})
        if len(ref_out) != 1:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "USE_CONCEPT ref_ids"})
    else:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "unknown kind"})

    out = dict(action_obj)
    out["opcode_u16"] = int(opcode_u16)
    out["imm_i64"] = imm_out
    out["ref_ids"] = ref_out
    out["flags_u32"] = int(flags_u32)
    return out


def hash_action_record_v1(action_obj: dict) -> tuple[str, bytes]:
    action = _require_action_record_v1(action_obj)
    raw = gcj1_canon_bytes(action)
    digest32 = _sha25632_count(raw)
    return _sha256_id_from_hex_digest32(digest32), bytes(digest32)


def actenc_det_v1(aHash32: bytes, p_u32: int) -> list[int]:
    if not isinstance(aHash32, (bytes, bytearray, memoryview)) or len(bytes(aHash32)) != 32:
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "aHash32"})
    p = _require_u32(p_u32, reason=DMPL_E_OPSET_MISMATCH)
    a = bytes(aHash32)

    out: list[int] = []
    for k in range(p):
        digest = _sha25632_count(_ACTENC_PREFIX + a + struct.pack("<I", int(k) & 0xFFFFFFFF))
        val_u32 = int.from_bytes(digest[0:4], byteorder="little", signed=False)
        centered_s32 = int(val_u32) - 2147483648
        u_k_q32 = int(centered_s32) << 1
        out.append(int(u_k_q32))
    return out


__all__ = [
    "make_noop_action_v1",
    "make_use_concept_action_v1",
    "hash_action_record_v1",
    "actenc_det_v1",
]

