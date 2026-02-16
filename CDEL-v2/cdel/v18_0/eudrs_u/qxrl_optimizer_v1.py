"""QXRL optimizer (Phase 4): SGD + momentum in Q32 (v1).

This module is RE2: deterministic, fail-closed, no floats.
"""

from __future__ import annotations

from ..omega_common_v1 import fail
from .qxrl_common_v1 import (
    OPTIMIZER_KIND_ADAMW_Q32_V1,
    OPTIMIZER_KIND_SGD_MOMENTUM_Q32_V1,
    REASON_QXRL_SCHEMA_INVALID,
)
from .qxrl_ops_v1 import QXRLStepCountersV1, add_sat, clip_abs_q32, mul_q32


def sgd_momentum_update_inplace_q32_v1(
    *,
    w_q32_s64: list[int],
    m_q32_s64: list[int],
    g_q32_s64: list[int],
    lr_q32_s64: int,
    momentum_q32_s64: int,
    grad_clip_abs_q32_s64: int | None,
    ctr: QXRLStepCountersV1,
) -> None:
    if not isinstance(w_q32_s64, list) or not isinstance(m_q32_s64, list) or not isinstance(g_q32_s64, list):
        fail(REASON_QXRL_SCHEMA_INVALID)
    if len(w_q32_s64) != len(m_q32_s64) or len(w_q32_s64) != len(g_q32_s64):
        fail(REASON_QXRL_SCHEMA_INVALID)
    lr = int(lr_q32_s64)
    mu = int(momentum_q32_s64)
    cap = None if grad_clip_abs_q32_s64 is None else int(grad_clip_abs_q32_s64)
    if cap is not None and cap < 0:
        fail(REASON_QXRL_SCHEMA_INVALID)

    for i in range(len(w_q32_s64)):
        g = int(g_q32_s64[i])
        if cap is not None:
            g = int(clip_abs_q32(g, cap))

        m_new = add_sat(int(mul_q32(mu, int(m_q32_s64[i]), ctr)), int(g), ctr)
        delta = -int(mul_q32(lr, int(m_new), ctr))
        w_new = add_sat(int(w_q32_s64[i]), int(delta), ctr)

        m_q32_s64[i] = int(m_new)
        w_q32_s64[i] = int(w_new)


def adamw_update_inplace_q32_v1(
    *,
    w_q32_s64: list[int],
    m1_q32_s64: list[int],
    m2_q32_s64: list[int],
    g_q32_s64: list[int],
    lr_q32_s64: int,
    beta1_q32_s64: int,
    beta2_q32_s64: int,
    eps_q32_s64: int,
    weight_decay_q32_s64: int,
    ctr: QXRLStepCountersV1,
) -> None:
    # Phase 5: optional, but verifier forbids acceptance. Keep fail-closed.
    _ = (w_q32_s64, m1_q32_s64, m2_q32_s64, g_q32_s64, lr_q32_s64, beta1_q32_s64, beta2_q32_s64, eps_q32_s64, weight_decay_q32_s64, ctr)
    fail(REASON_QXRL_SCHEMA_INVALID)


def optimizer_update_inplace_q32_v1(
    *,
    optimizer_kind: str,
    w_q32_s64: list[int],
    m_q32_s64: list[int],
    g_q32_s64: list[int],
    lr_q32_s64: int,
    momentum_q32_s64: int,
    grad_clip_abs_q32_s64: int | None,
    ctr: QXRLStepCountersV1,
) -> None:
    kind = str(optimizer_kind).strip()
    if kind == OPTIMIZER_KIND_SGD_MOMENTUM_Q32_V1:
        sgd_momentum_update_inplace_q32_v1(
            w_q32_s64=w_q32_s64,
            m_q32_s64=m_q32_s64,
            g_q32_s64=g_q32_s64,
            lr_q32_s64=lr_q32_s64,
            momentum_q32_s64=momentum_q32_s64,
            grad_clip_abs_q32_s64=grad_clip_abs_q32_s64,
            ctr=ctr,
        )
        return
    if kind == OPTIMIZER_KIND_ADAMW_Q32_V1:
        # This path is intentionally not supported for Phase 5 promotions.
        fail(REASON_QXRL_SCHEMA_INVALID)
    fail(REASON_QXRL_SCHEMA_INVALID)


__all__ = [
    "adamw_update_inplace_q32_v1",
    "optimizer_update_inplace_q32_v1",
    "sgd_momentum_update_inplace_q32_v1",
]
