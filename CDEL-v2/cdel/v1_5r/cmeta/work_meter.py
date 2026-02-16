"""Work meter utilities for v1.5r."""

from __future__ import annotations

from typing import Any


_CURRENT_METER: "WorkMeter | None" = None


class WorkMeter:
    """Minimal work meter accumulator for v1.5r."""

    def __init__(self, epoch_id: str, collection_rules_hash: str) -> None:
        self.epoch_id = epoch_id
        self.collection_rules_hash = collection_rules_hash
        self._counts = {
            "env_steps_total": 0,
            "oracle_calls_total": 0,
            "verifier_gas_total": 0,
            "bytes_hashed_total": 0,
            "candidates_fully_evaluated": 0,
            "short_circuits_total": 0,
        }

    def bump(self, field: str, amount: int) -> None:
        if field not in self._counts:
            return
        self._counts[field] += int(amount)

    def add(self, delta: dict[str, Any]) -> None:
        for key in self._counts:
            if key in delta:
                self._counts[key] += int(delta.get(key, 0))

    def snapshot(self) -> dict[str, Any]:
        payload = {
            "schema": "work_meter_v1",
            "schema_version": 1,
            "epoch_id": self.epoch_id,
            "env_steps_total": int(self._counts["env_steps_total"]),
            "oracle_calls_total": int(self._counts["oracle_calls_total"]),
            "verifier_gas_total": int(self._counts["verifier_gas_total"]),
            "bytes_hashed_total": int(self._counts["bytes_hashed_total"]),
            "candidates_fully_evaluated": int(self._counts["candidates_fully_evaluated"]),
            "short_circuits_total": int(self._counts["short_circuits_total"]),
            "meter_version": 1,
            "collection_rules_hash": self.collection_rules_hash,
        }
        return payload


def set_current_meter(meter: "WorkMeter | None") -> None:
    global _CURRENT_METER
    _CURRENT_METER = meter


def get_current_meter() -> "WorkMeter | None":
    return _CURRENT_METER


def _bump(field: str, amount: int) -> None:
    meter = _CURRENT_METER
    if meter is None:
        return
    meter.bump(field, amount)


def bump_env_steps(amount: int = 1) -> None:
    _bump("env_steps_total", amount)


def bump_oracle_calls(amount: int = 1) -> None:
    _bump("oracle_calls_total", amount)


def bump_verifier_gas(amount: int = 1) -> None:
    _bump("verifier_gas_total", amount)


def bump_bytes_hashed(amount: int = 1) -> None:
    _bump("bytes_hashed_total", amount)


def bump_candidates_fully_evaluated(amount: int = 1) -> None:
    _bump("candidates_fully_evaluated", amount)


def bump_short_circuits(amount: int = 1) -> None:
    _bump("short_circuits_total", amount)


def new_work_meter(epoch_id: str, collection_rules_hash: str) -> dict[str, Any]:
    return {
        "schema": "work_meter_v1",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "env_steps_total": 0,
        "oracle_calls_total": 0,
        "verifier_gas_total": 0,
        "bytes_hashed_total": 0,
        "candidates_fully_evaluated": 0,
        "short_circuits_total": 0,
        "meter_version": 1,
        "collection_rules_hash": collection_rules_hash,
    }


def compare_workvec(a: dict[str, Any], b: dict[str, Any]) -> int:
    """Return -1 if a dominates b, 0 if equal, 1 if b dominates a, 2 otherwise."""
    order = [
        ("verifier_gas_total", -1),
        ("env_steps_total", -1),
        ("oracle_calls_total", -1),
        ("bytes_hashed_total", -1),
        ("candidates_fully_evaluated", -1),
        ("short_circuits_total", 1),
    ]
    better_a = False
    better_b = False
    for key, direction in order:
        av = int(a.get(key, 0))
        bv = int(b.get(key, 0))
        if av == bv:
            continue
        if direction == -1:
            if av < bv:
                better_a = True
            else:
                better_b = True
        else:
            if av > bv:
                better_a = True
            else:
                better_b = True
        if better_a and better_b:
            return 2
    if better_a and not better_b:
        return -1
    if better_b and not better_a:
        return 1
    return 0
