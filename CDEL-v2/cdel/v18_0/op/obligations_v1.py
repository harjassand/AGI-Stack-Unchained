"""Tier-1 local obligation closure for ACTIONSEQ operators."""

from __future__ import annotations

from collections import Counter
from typing import Any


def make_obligation_state() -> Counter[str]:
    return Counter()


def apply_obligation_bundle(state: Counter[str], bundle: dict[str, Any]) -> None:
    requires = bundle.get("requires", [])
    generates = bundle.get("generates", [])
    discharges = bundle.get("discharges", [])
    if not isinstance(requires, list) or not isinstance(generates, list) or not isinstance(discharges, list):
        raise RuntimeError("INVALID:LOCAL_OBLIGATIONS_UNDISCHARGED")

    for req_any in requires:
        req = str(req_any).strip()
        if not req:
            continue
        if state[req] <= 0:
            raise RuntimeError("INVALID:LOCAL_OBLIGATIONS_UNDISCHARGED")
        state[req] -= 1

    for gen_any in generates:
        gen = str(gen_any).strip()
        if not gen:
            continue
        state[gen] += 1

    for dis_any in discharges:
        dis = str(dis_any).strip()
        if not dis:
            continue
        if state[dis] <= 0:
            raise RuntimeError("INVALID:LOCAL_OBLIGATIONS_UNDISCHARGED")
        state[dis] -= 1


def assert_no_blocking_obligations(state: Counter[str]) -> None:
    blocking = sorted(k for k, v in state.items() if int(v) > 0 and str(k).startswith("BLOCKING:"))
    if blocking:
        raise RuntimeError("INVALID:LOCAL_OBLIGATIONS_UNDISCHARGED")


__all__ = ["apply_obligation_bundle", "assert_no_blocking_obligations", "make_obligation_state"]

