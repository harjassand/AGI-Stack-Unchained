"""Deterministic Q32 preference-contrast math for QXRL (MVP).

This module is RE2:
- no floats
- no RNG
- fail-closed on malformed inputs
"""

from __future__ import annotations

from typing import Any, Final

from ..omega_common_v1 import Q32_ONE, fail
from .qxrl_common_v1 import REASON_QXRL_SCHEMA_INVALID
from .qxrl_opset_math_v1 import div_q32_pos_rne_v1
from .qxrl_ops_v1 import QXRLStepCountersV1, add_sat, mul_q32

PREFERENCE_FEATURE_KIND_PROPOSAL_HASH_HEAD32_Q32_V1: Final[str] = "PROPOSAL_HASH_HEAD32_Q32_V1"
PREFERENCE_POLYNOMIAL_ID_Q32_LOGSIGMOID_NEG_V1: Final[str] = (
    "sha256:72d388ee9edc704d650c758f1ef97f49cee0e57ded74517683579fb69729b256"
)
PREFERENCE_HEAD_WEIGHT_TENSOR_NAME: Final[str] = "qxrl/pref_head/w"

_DOMAIN_MIN_Q32: Final[int] = -(4 * Q32_ONE)
_DOMAIN_MAX_Q32: Final[int] = 4 * Q32_ONE
# -logsigmoid(x) ~= c0 + c1*x + c2*x^2 + c3*x^3 on clamped domain [-4, 4].
_COEFFS_Q32: Final[tuple[int, int, int, int]] = (
    2977044471,  # ln(2)
    -2147483648,  # -0.5
    536870912,  # 0.125
    0,
)


def _require_sha256(value: Any) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value.split(":", 1)[1]) != 64:
        fail(REASON_QXRL_SCHEMA_INVALID)
    return value


def _clamp_q32(x_q32_s64: int, *, lo_q32: int, hi_q32: int) -> int:
    x = int(x_q32_s64)
    lo = int(lo_q32)
    hi = int(hi_q32)
    if lo > hi:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def _poly_eval_q32(x_q32_s64: int, coeffs_q32: tuple[int, int, int, int], ctr: QXRLStepCountersV1) -> int:
    x = int(x_q32_s64)
    c0, c1, c2, c3 = [int(v) for v in coeffs_q32]
    x2 = mul_q32(x, x, ctr)
    x3 = mul_q32(x2, x, ctr)
    out = int(c0)
    out = add_sat(out, mul_q32(c1, x, ctr), ctr)
    out = add_sat(out, mul_q32(c2, x2, ctr), ctr)
    out = add_sat(out, mul_q32(c3, x3, ctr), ctr)
    if out < 0:
        return 0
    return int(out)


def _poly_derivative_q32(x_q32_s64: int, coeffs_q32: tuple[int, int, int, int], ctr: QXRLStepCountersV1) -> int:
    x = int(x_q32_s64)
    c1 = int(coeffs_q32[1])
    c2 = int(coeffs_q32[2])
    c3 = int(coeffs_q32[3])
    two_c2 = c2 * 2
    three_c3 = c3 * 3
    x2 = mul_q32(x, x, ctr)
    out = int(c1)
    out = add_sat(out, mul_q32(two_c2, x, ctr), ctr)
    out = add_sat(out, mul_q32(three_c3, x2, ctr), ctr)
    return int(out)


def resolve_preference_polynomial_id(polynomial_id: str) -> tuple[int, int, int, int]:
    pid = _require_sha256(polynomial_id)
    if pid != PREFERENCE_POLYNOMIAL_ID_Q32_LOGSIGMOID_NEG_V1:
        fail(REASON_QXRL_SCHEMA_INVALID)
    return _COEFFS_Q32


def feature_q32_from_proposal_hash(proposal_hash: str) -> int:
    value = _require_sha256(proposal_hash)
    head = value.split(":", 1)[1][:8]
    try:
        raw_u32 = int(head, 16)
    except Exception:
        fail(REASON_QXRL_SCHEMA_INVALID)
        return 0
    if raw_u32 >= 0x80000000:
        raw_i32 = raw_u32 - 0x100000000
    else:
        raw_i32 = raw_u32
    return int(raw_i32)


def preference_score_q32(*, weight_q32_s64: int, feature_q32_s64: int, ctr: QXRLStepCountersV1) -> int:
    return int(mul_q32(int(weight_q32_s64), int(feature_q32_s64), ctr))


def preference_contrast_loss_and_slope_q32(
    *,
    score_winner_q32_s64: int,
    score_loser_q32_s64: int,
    margin_q32_s64: int,
    temperature_q32_pos_s64: int,
    polynomial_id: str,
    ctr: QXRLStepCountersV1,
) -> tuple[int, int]:
    if int(temperature_q32_pos_s64) <= 0:
        fail(REASON_QXRL_SCHEMA_INVALID)

    coeffs = resolve_preference_polynomial_id(polynomial_id)
    delta = add_sat(int(score_winner_q32_s64), -int(score_loser_q32_s64), ctr)
    delta = add_sat(delta, -int(margin_q32_s64), ctr)
    x_q32 = int(
        div_q32_pos_rne_v1(
            numer_q32_s64=int(delta),
            denom_q32_pos_s64=int(temperature_q32_pos_s64),
            ctr=ctr,
        )
    )
    x_clamped = _clamp_q32(x_q32, lo_q32=_DOMAIN_MIN_Q32, hi_q32=_DOMAIN_MAX_Q32)
    loss_q32 = _poly_eval_q32(x_clamped, coeffs, ctr)
    dloss_dx_q32 = _poly_derivative_q32(x_clamped, coeffs, ctr)
    inv_temp_q32 = int(
        div_q32_pos_rne_v1(
            numer_q32_s64=int(Q32_ONE),
            denom_q32_pos_s64=int(temperature_q32_pos_s64),
            ctr=ctr,
        )
    )
    dloss_ddelta_q32 = int(mul_q32(int(dloss_dx_q32), int(inv_temp_q32), ctr))
    return int(loss_q32), int(dloss_ddelta_q32)


__all__ = [
    "PREFERENCE_FEATURE_KIND_PROPOSAL_HASH_HEAD32_Q32_V1",
    "PREFERENCE_HEAD_WEIGHT_TENSOR_NAME",
    "PREFERENCE_POLYNOMIAL_ID_Q32_LOGSIGMOID_NEG_V1",
    "feature_q32_from_proposal_hash",
    "preference_contrast_loss_and_slope_q32",
    "preference_score_q32",
    "resolve_preference_polynomial_id",
]
