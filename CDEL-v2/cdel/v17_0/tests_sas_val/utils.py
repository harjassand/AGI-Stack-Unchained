from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed
from cdel.v17_0.val.val_decode_aarch64_v1 import decode_trace_py, decode_trace_rs, decoded_trace_hash
from cdel.v17_0.val.val_isa_v1 import parse_policy
from cdel.v17_0.val.val_lift_ir_v1 import lift_ir_hash, lift_ir_py, lift_ir_rs
from cdel.v17_0.val.val_verify_safety_v1 import verify_safety


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def campaign_root() -> Path:
    return repo_root() / "campaigns" / "rsi_sas_val_v17_0"


def load_policy_obj() -> Any:
    obj = load_canon_json(campaign_root() / "sas_val_policy_v1.json")
    if not isinstance(obj, dict):
        raise ValueError("INVALID:SCHEMA_FAIL")
    return parse_policy(obj)


def load_template_patch_manifest() -> dict[str, Any]:
    obj = load_canon_json(campaign_root() / "patches" / "val_patch_manifest_v1.json")
    if not isinstance(obj, dict):
        raise ValueError("INVALID:SCHEMA_FAIL")
    return obj


def build_manifest_for_code(code_bytes: bytes) -> dict[str, Any]:
    manifest = dict(load_template_patch_manifest())
    manifest["code_bytes_b64"] = base64.b64encode(code_bytes).decode("ascii")
    manifest["declared_code_len_u32"] = len(code_bytes)
    payload = dict(manifest)
    payload.pop("patch_id", None)
    manifest["patch_id"] = sha256_prefixed(canon_bytes(payload))
    return manifest


def safety_receipt_for_code(code_bytes: bytes) -> dict[str, Any]:
    policy = load_policy_obj()
    manifest = build_manifest_for_code(code_bytes)
    decoded_py = decode_trace_py(code_bytes)
    decoded_rs = decode_trace_rs(code_bytes)
    if decoded_trace_hash(decoded_py) != decoded_trace_hash(decoded_rs):
        raise ValueError("INVALID:VAL_DUAL_DECODER_DIVERGENCE")
    lifted_py = lift_ir_py(decoded_py)
    lifted_rs = lift_ir_rs(decoded_py)
    if lift_ir_hash(lifted_py) != lift_ir_hash(lifted_rs):
        raise ValueError("INVALID:VAL_DUAL_LIFTER_DIVERGENCE")
    return verify_safety(
        decoded_trace=decoded_py,
        lifted_ir=lifted_py,
        patch_manifest=manifest,
        policy=policy,
    )


def load_redteam_patch(name: str) -> bytes:
    return (campaign_root() / "redteam_patches" / name).read_bytes()
