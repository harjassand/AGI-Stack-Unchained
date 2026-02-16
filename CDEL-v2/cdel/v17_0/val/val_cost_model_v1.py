"""Deterministic instruction-cost model for VAL v17.0."""

from __future__ import annotations

from typing import Any

INSN_COST = {
    "ldr": 2,
    "str": 2,
    "ld1": 4,
    "st1": 4,
    "add": 1,
    "sub": 1,
    "subs": 1,
    "eor": 1,
    "and": 1,
    "orr": 1,
    "mov": 1,
    "cmp": 1,
    "ror": 1,
    "lsr": 1,
    "lsl": 1,
    "rev32": 1,
    "sha256h": 6,
    "sha256h2": 6,
    "sha256su0": 4,
    "sha256su1": 4,
    "b.ne": 1,
    "ret": 1,
}


class ValCostModelError(ValueError):
    pass


def estimate_val_cycles(decoded_trace: dict[str, Any], *, blocks_len: int, baseline_mode: bool) -> int:
    if blocks_len < 0:
        raise ValCostModelError("INVALID:SCHEMA_FAIL")

    if baseline_mode:
        # Baseline includes process-spawn overhead; deterministic and intentionally conservative.
        return int((blocks_len * 1200) + 250_000)

    per_iter = 0
    for row in decoded_trace.get("instructions", []):
        mnemonic = str(row.get("mnemonic", "")).lower()
        per_iter += int(INSN_COST.get(mnemonic, 12))
    if per_iter <= 0:
        per_iter = 1

    return int(max(1, blocks_len) * per_iter)


def gate_valcycles(*, candidate: int, baseline: int, num: int, den: int) -> bool:
    if baseline <= 0 or candidate < 0 or num <= 0 or den <= 0:
        return False
    return candidate * den <= baseline * num


__all__ = [
    "ValCostModelError",
    "estimate_val_cycles",
    "gate_valcycles",
]
