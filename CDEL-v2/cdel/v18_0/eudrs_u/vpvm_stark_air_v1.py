"""VPVM Q32 AIR (v1).

v1 implements a minimal AIR used by the STARK-VM proof path:
  - a deterministic commitment machine trace that proves correct rollhash32x2
    accumulator updates over five committed streams:
      program, lut, dataset, weights_before, weights_after

This keeps the binding checks *inside* the STARK proof, and is a sound drop-in
replacement for the prior placeholder proof format.

NOTE: The full VPVM instruction-set AIR (Q32 saturating ISA + RAM argument) is
roadmapped but not required for the v1 binding proof shipped here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from .gld_field_v1 import P_GOLDILOCKS
from .pclp_common_v1 import ROLLHASH32X2_BATCH_U32_PER_ROW_V1


AIR_ID_VPVM_Q32_V1: Final[str] = "vpvm_q32_air_v1"

# Stream IDs (fixed).
STREAM_PROGRAM: Final[int] = 0
STREAM_LUT: Final[int] = 1
STREAM_DATASET: Final[int] = 2
STREAM_WEIGHTS_BEFORE: Final[int] = 3
STREAM_WEIGHTS_AFTER: Final[int] = 4


@dataclass(frozen=True, slots=True)
class VpvmCommitTraceLayoutV1:
    # Main trace columns.
    # One-hot selectors:
    #   sel_program, sel_lut, sel_dataset, sel_w_before, sel_w_after, sel_pad
    # plus a fixed-size batch of u32 items.
    MAIN_COLS: tuple[str, ...] = (
        "sel_program",
        "sel_lut",
        "sel_dataset",
        "sel_w_before",
        "sel_w_after",
        "sel_pad",
        *tuple(f"item{i}" for i in range(int(ROLLHASH32X2_BATCH_U32_PER_ROW_V1))),
    )

    # Aux trace columns: two accumulators per stream (f0/f1).
    AUX_COLS: tuple[str, ...] = (
        "acc_program_f0",
        "acc_program_f1",
        "acc_lut_f0",
        "acc_lut_f1",
        "acc_dataset_f0",
        "acc_dataset_f1",
        "acc_w_before_f0",
        "acc_w_before_f1",
        "acc_w_after_f0",
        "acc_w_after_f1",
    )


def eval_transition_constraints_v1(
    *,
    cur_main: list[int],
    nxt_main: list[int],
    cur_aux: list[int],
    nxt_aux: list[int],
    r_bind_f0: int,
    r_bind_f1: int,
) -> list[int]:
    """Evaluate transition constraints at a single point (degree <= 2).

    Inputs are lists of field elements for the row at x (cur_*) and row at x*ω (nxt_*).
    """

    # Unpack main.
    (
        sel_program,
        sel_lut,
        sel_dataset,
        sel_w_before,
        sel_w_after,
        sel_pad,
        *items,
    ) = [int(v) % P_GOLDILOCKS for v in cur_main]
    (
        sel_program_n,
        sel_lut_n,
        sel_dataset_n,
        sel_w_before_n,
        sel_w_after_n,
        sel_pad_n,
        *_items_n,
    ) = [int(v) % P_GOLDILOCKS for v in nxt_main]

    # Unpack aux (order per layout).
    (
        acc_p0,
        acc_p1,
        acc_l0,
        acc_l1,
        acc_d0,
        acc_d1,
        acc_b0,
        acc_b1,
        acc_a0,
        acc_a1,
    ) = [int(v) % P_GOLDILOCKS for v in cur_aux]
    (
        acc_p0_n,
        acc_p1_n,
        acc_l0_n,
        acc_l1_n,
        acc_d0_n,
        acc_d1_n,
        acc_b0_n,
        acc_b1_n,
        acc_a0_n,
        acc_a1_n,
    ) = [int(v) % P_GOLDILOCKS for v in nxt_aux]

    r0 = int(r_bind_f0) % P_GOLDILOCKS
    r1 = int(r_bind_f1) % P_GOLDILOCKS

    out: list[int] = []

    # Boolean constraints for selectors (b*(b-1)=0).
    for b in [sel_program, sel_lut, sel_dataset, sel_w_before, sel_w_after, sel_pad]:
        out.append((b * (b - 1)) % P_GOLDILOCKS)

    # One-hot: sum = 1.
    out.append((sel_program + sel_lut + sel_dataset + sel_w_before + sel_w_after + sel_pad - 1) % P_GOLDILOCKS)

    # Padding is suffix: if pad then next is pad.
    out.append((sel_pad * (1 - sel_pad_n)) % P_GOLDILOCKS)

    # If pad, item must be 0.
    for it in items:
        out.append((sel_pad * int(it)) % P_GOLDILOCKS)

    # Accumulator update helpers.
    def _rollhash_block(acc: int, r: int, its: list[int]) -> int:
        """Rollhash update across a fixed batch of items (degree-1 in acc/items).

        Important: do not branch on selector values here. This function is evaluated
        on the LDE domain where selectors are not necessarily 0/1, so the AIR must be
        expressed as algebraic constraints only.
        """

        rr = int(r) % P_GOLDILOCKS
        a = int(acc) % P_GOLDILOCKS
        for it in its:
            a = (a * rr + int(it)) % P_GOLDILOCKS
        return int(a)

    def _upd_block(acc: int, sel: int, r: int, its: list[int]) -> int:
        # Algebraic gating: acc_next = sel*rollhash(acc, its) + (1-sel)*acc.
        s = int(sel) % P_GOLDILOCKS
        upd = _rollhash_block(int(acc), int(r), its)
        return (s * int(upd) + (1 - s) * (int(acc) % P_GOLDILOCKS)) % P_GOLDILOCKS

    # Program.
    out.append((acc_p0_n - _upd_block(acc_p0, sel_program, r0, list(items))) % P_GOLDILOCKS)
    out.append((acc_p1_n - _upd_block(acc_p1, sel_program, r1, list(items))) % P_GOLDILOCKS)
    # LUT.
    out.append((acc_l0_n - _upd_block(acc_l0, sel_lut, r0, list(items))) % P_GOLDILOCKS)
    out.append((acc_l1_n - _upd_block(acc_l1, sel_lut, r1, list(items))) % P_GOLDILOCKS)
    # Dataset.
    out.append((acc_d0_n - _upd_block(acc_d0, sel_dataset, r0, list(items))) % P_GOLDILOCKS)
    out.append((acc_d1_n - _upd_block(acc_d1, sel_dataset, r1, list(items))) % P_GOLDILOCKS)
    # Weights before.
    out.append((acc_b0_n - _upd_block(acc_b0, sel_w_before, r0, list(items))) % P_GOLDILOCKS)
    out.append((acc_b1_n - _upd_block(acc_b1, sel_w_before, r1, list(items))) % P_GOLDILOCKS)
    # Weights after.
    out.append((acc_a0_n - _upd_block(acc_a0, sel_w_after, r0, list(items))) % P_GOLDILOCKS)
    out.append((acc_a1_n - _upd_block(acc_a1, sel_w_after, r1, list(items))) % P_GOLDILOCKS)

    # Optional sanity: if a selector is 1, it must remain 0/1 next row as well (already boolean).
    # Enforce next row booleans too via verifier openings at x*ω (covered by random queries).
    for b in [sel_program_n, sel_lut_n, sel_dataset_n, sel_w_before_n, sel_w_after_n, sel_pad_n]:
        out.append((b * (b - 1)) % P_GOLDILOCKS)

    return [int(v) % P_GOLDILOCKS for v in out]


def mix_constraints_v1(*, constraints: list[int], alpha_mix: int) -> int:
    """Mix a vector of constraints into one field element via powers of alpha_mix."""

    a = int(alpha_mix) % P_GOLDILOCKS
    acc = 0
    pow_a = 1
    for c in constraints:
        acc = (acc + int(c) * pow_a) % P_GOLDILOCKS
        pow_a = (pow_a * a) % P_GOLDILOCKS
    return int(acc)


__all__ = [
    "AIR_ID_VPVM_Q32_V1",
    "STREAM_DATASET",
    "STREAM_LUT",
    "STREAM_PROGRAM",
    "STREAM_WEIGHTS_AFTER",
    "STREAM_WEIGHTS_BEFORE",
    "VpvmCommitTraceLayoutV1",
    "eval_transition_constraints_v1",
    "mix_constraints_v1",
]
