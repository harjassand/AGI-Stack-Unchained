"""Bucketing rules for ontology v3."""

from __future__ import annotations

from typing import Any

from ..canon import CanonError


def _wrap_i32(value: int) -> int:
    value = int(value) & 0xFFFFFFFF
    if value >= 2**31:
        value -= 2**32
    return value


def validate_bucketer_spec(bucketer: dict[str, Any], output_type: str) -> None:
    if not isinstance(bucketer, dict):
        raise CanonError("bucketer must be object")
    kind = bucketer.get("kind")
    if kind not in {"bool01", "sign3", "mod_m", "clamp_r"}:
        raise CanonError("bucketer kind invalid")
    if output_type == "bool" and kind != "bool01":
        raise CanonError("bool output requires bool01 bucketer")
    if output_type == "i32" and kind == "bool01":
        raise CanonError("bool01 bucketer requires bool output")

    if kind == "mod_m":
        if "r" in bucketer:
            raise CanonError("mod_m bucketer must not include r")
        m = bucketer.get("m")
        if not isinstance(m, int) or m < 2 or m > 256:
            raise CanonError("mod_m bucketer m out of bounds")
        return
    if kind == "clamp_r":
        if "m" in bucketer:
            raise CanonError("clamp_r bucketer must not include m")
        r = bucketer.get("r")
        if not isinstance(r, int) or r < 1 or r > 1024:
            raise CanonError("clamp_r bucketer r out of bounds")
        return
    if kind in {"bool01", "sign3"}:
        if "m" in bucketer or "r" in bucketer:
            raise CanonError("bucketer fields invalid")
        return


def apply_bucketer(value: Any, bucketer: dict[str, Any], output_type: str) -> int:
    kind = bucketer.get("kind")
    if output_type == "bool":
        if kind != "bool01":
            raise CanonError("bool output requires bool01 bucketer")
        if not isinstance(value, bool):
            raise CanonError("bucketer expected bool input")
        return 1 if value else 0
    if output_type == "i32":
        if isinstance(value, bool) or not isinstance(value, int):
            raise CanonError("bucketer expected i32 input")
        raw = _wrap_i32(value)
        if kind == "sign3":
            if raw < 0:
                return -1
            if raw > 0:
                return 1
            return 0
        if kind == "mod_m":
            m = int(bucketer.get("m"))
            return int(((raw % m) + m) % m)
        if kind == "clamp_r":
            r = int(bucketer.get("r"))
            if raw < -r:
                return -r
            if raw > r:
                return r
            return raw
        raise CanonError("bucketer kind invalid")
    raise CanonError("bucketer output_type invalid")
