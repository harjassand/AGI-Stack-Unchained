from __future__ import annotations

import pytest

from cdel.v18_0.eudrs_u.eudrs_u_q32ops_v1 import (
    S64_MAX,
    S64_MIN,
    add_sat,
    argmax_det,
    dot_q32_shift_each_dim_v1,
    dot_q32_shift_end_v1,
    mul_q32,
    topk_det,
)
from cdel.v18_0.omega_common_v1 import OmegaV18Error


def test_add_sat_vectors() -> None:
    assert add_sat(S64_MAX, 1) == S64_MAX
    assert add_sat(S64_MIN, -1) == S64_MIN


def test_mul_q32_vectors() -> None:
    Q1 = 1 << 32
    QH = 1 << 31
    assert mul_q32(Q1, Q1) == Q1
    assert mul_q32(QH, QH) == 1073741824  # 0.25 in Q32
    assert mul_q32(-Q1, QH) == -QH
    assert mul_q32(S64_MAX, S64_MAX) == S64_MAX


def test_dot_variants_differentiating_vector() -> None:
    x = [(1 << 32) - 1, (1 << 32) - 1]  # 2^32 - 1
    y = [(1 << 32) + 1, (1 << 32) + 1]  # 2^32 + 1
    assert dot_q32_shift_each_dim_v1(x, y) == 8589934590
    assert dot_q32_shift_end_v1(x, y) == 8589934591


def test_argmax_det_ties_lowest_index() -> None:
    assert argmax_det([5, 5, 4]) == 0


def test_topk_det_sort_and_tiebreak() -> None:
    assert topk_det([(1, 2), (1, 1), (2, 3)], 2) == [(2, 3), (1, 1)]


def test_topk_det_negative_k_rejected() -> None:
    with pytest.raises(OmegaV18Error):
        topk_det([(1, 1)], -1)

