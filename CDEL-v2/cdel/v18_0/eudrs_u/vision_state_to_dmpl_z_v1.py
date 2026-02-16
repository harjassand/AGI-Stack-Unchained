"""Deterministic Vision-State -> DMPL latent adapter (Stage 4, v1).

This module is RE2-authoritative logic used by Stage4 verifiers/campaigns.
It maps QXWMR state bytes to QXRL tokens, runs deterministic QXRL encoder
forward, and projects to DMPL state dimension.
"""

from __future__ import annotations

from typing import Any, Callable

from ..omega_common_v1 import fail
from .dmpl_train_sgd_v1 import encode_tensor_q32_v1
from .eudrs_u_artifact_refs_v1 import require_artifact_ref_v1
from .qxrl_common_v1 import ENCODER_KIND_TSAE_V1, parse_qxrl_invsqrt_lut_manifest_v1
from .qxrl_forward_qre_v1 import parse_qxrl_model_manifest_v1
from .qxrl_forward_qre_v1 import forward_encoder_qre_v1
from .qxrl_forward_tsae_v1 import forward_encoder_tsae_v1
from .qxrl_opset_math_v1 import parse_invsqrt_lut_bin_v1
from .qxrl_ops_v1 import QXRLStepCountersV1
from .qxrl_train_replay_v1 import load_and_verify_weights_manifest_v1, weights_view_from_manifest
from .vision_common_v1 import REASON_VISION4_BINDING_MISMATCH


TOKEN_ADAPTER_ID_V1 = "vision_state_to_dmpl_z_v1"


def state_bytes_to_tokens_v1(
    *,
    qxwmr_state_bytes: bytes,
    seq_len_u32: int,
    vocab_size_u32: int,
    token_adapter_id: str,
) -> list[int]:
    """Map packed QXWMR state bytes to BYTE_TOK_257_V1 tokens deterministically."""

    if str(token_adapter_id).strip() != TOKEN_ADAPTER_ID_V1:
        fail(REASON_VISION4_BINDING_MISMATCH)
    seq_len = int(seq_len_u32)
    vocab = int(vocab_size_u32)
    if seq_len < 1 or vocab < 257:
        fail(REASON_VISION4_BINDING_MISMATCH)

    raw = bytes(qxwmr_state_bytes)
    out = bytearray()
    take = min(len(raw), seq_len)
    if take > 0:
        out += raw[:take]
    if len(out) < seq_len:
        out += b"\x00" * int(seq_len - len(out))

    toks = [int(b) for b in bytes(out)]
    for t in toks:
        if int(t) < 0 or int(t) >= int(vocab):
            fail(REASON_VISION4_BINDING_MISMATCH)
    return toks


def project_latent_to_dmpl_dim_v1(
    *,
    z_q32_s64: list[int],
    d_u32: int,
    max_abs_z_q32: int | None = None,
) -> list[int]:
    """Project QXRL latent to DMPL `d_u32` deterministically (truncate/pad)."""

    d = int(d_u32)
    if d < 1:
        fail(REASON_VISION4_BINDING_MISMATCH)
    out: list[int] = [0] * d
    n = min(int(len(z_q32_s64)), d)
    for i in range(n):
        out[i] = int(z_q32_s64[i])
    if max_abs_z_q32 is not None:
        cap = int(max_abs_z_q32)
        if cap < 0:
            fail(REASON_VISION4_BINDING_MISMATCH)
        for v in out:
            if abs(int(v)) > cap:
                fail(REASON_VISION4_BINDING_MISMATCH)
    return out


def vision_state_to_dmpl_z_v1(
    *,
    qxwmr_state_bytes: bytes,
    qxrl_model_manifest_obj: dict[str, Any],
    weights_manifest_obj: dict[str, Any],
    registry_loader: Callable[[dict[str, Any]], bytes],
    token_adapter_id: str = TOKEN_ADAPTER_ID_V1,
) -> list[int]:
    """Compute deterministic QXRL latent `z` for a packed QXWMR state."""

    model = parse_qxrl_model_manifest_v1(dict(qxrl_model_manifest_obj))
    weights_manifest = load_and_verify_weights_manifest_v1(
        weights_manifest_obj=dict(weights_manifest_obj),
        registry_loader=registry_loader,
    )
    weights_view = weights_view_from_manifest(model=model, weights_manifest=weights_manifest)

    tokens = state_bytes_to_tokens_v1(
        qxwmr_state_bytes=bytes(qxwmr_state_bytes),
        seq_len_u32=int(model.seq_len_u32),
        vocab_size_u32=int(model.vocab_size_u32),
        token_adapter_id=str(token_adapter_id),
    )

    ctr = QXRLStepCountersV1()
    if str(model.encoder_kind).strip() == ENCODER_KIND_TSAE_V1:
        lut_ref = require_artifact_ref_v1(model.invsqrt_lut_manifest_ref, reason=REASON_VISION4_BINDING_MISMATCH)
        lut_manifest_obj = parse_qxrl_invsqrt_lut_manifest_v1(bytes(registry_loader(dict(lut_ref))))
        lut_bin_ref = require_artifact_ref_v1(lut_manifest_obj.table_bin_ref, reason=REASON_VISION4_BINDING_MISMATCH)
        lut_table = parse_invsqrt_lut_bin_v1(
            bytes(registry_loader(dict(lut_bin_ref))),
            expected_size_u32=int(lut_manifest_obj.table_size_u32),
        )
        cache = forward_encoder_tsae_v1(
            tokens_u32=list(tokens),
            model=model,
            weights=weights_view,
            lut_table_q32_s64=list(lut_table),
            ctr=ctr,
            count_tokens=False,
        )
        return [int(v) for v in cache.z_q32_s64]

    cache = forward_encoder_qre_v1(
        tokens_u32=list(tokens),
        model=model,
        weights=weights_view,
        ctr=ctr,
        count_tokens=False,
    )
    return [int(v) for v in cache.z_q32_s64]


def vision_state_to_dmpl_tensor_bytes_v1(
    *,
    qxwmr_state_bytes: bytes,
    qxrl_model_manifest_obj: dict[str, Any],
    weights_manifest_obj: dict[str, Any],
    registry_loader: Callable[[dict[str, Any]], bytes],
    d_u32: int,
    max_abs_z_q32: int | None = None,
    token_adapter_id: str = TOKEN_ADAPTER_ID_V1,
) -> bytes:
    """Encode deterministic DMPL tensor bytes from a packed QXWMR state."""

    z_model = vision_state_to_dmpl_z_v1(
        qxwmr_state_bytes=bytes(qxwmr_state_bytes),
        qxrl_model_manifest_obj=dict(qxrl_model_manifest_obj),
        weights_manifest_obj=dict(weights_manifest_obj),
        registry_loader=registry_loader,
        token_adapter_id=str(token_adapter_id),
    )
    z_dmpl = project_latent_to_dmpl_dim_v1(
        z_q32_s64=z_model,
        d_u32=int(d_u32),
        max_abs_z_q32=max_abs_z_q32,
    )
    return encode_tensor_q32_v1(dims_u32=[int(d_u32)], values_i64=[int(v) for v in z_dmpl])


__all__ = [
    "TOKEN_ADAPTER_ID_V1",
    "project_latent_to_dmpl_dim_v1",
    "state_bytes_to_tokens_v1",
    "vision_state_to_dmpl_tensor_bytes_v1",
    "vision_state_to_dmpl_z_v1",
]
