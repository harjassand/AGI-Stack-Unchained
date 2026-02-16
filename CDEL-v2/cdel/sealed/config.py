"""Config parsing for sealed evaluator settings."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cdel.sealed.evalue import AlphaSchedule, parse_alpha_schedule, parse_decimal


@dataclass(frozen=True)
class SealedConfig:
    alpha_total: Decimal
    alpha_schedule: AlphaSchedule
    eval_harness_id: str
    eval_harness_hash: str
    eval_suite_hash: str
    allowed_keys: dict[str, str]


def load_sealed_config(data: dict, require_keys: bool = True) -> SealedConfig:
    sealed = data.get("sealed") or {}
    if not isinstance(sealed, dict):
        raise ValueError("sealed config must be an object")

    alpha_total_raw = sealed.get("alpha_total")
    if alpha_total_raw is None:
        alpha_total_raw = (data.get("stat_cert") or {}).get("alpha_total")
    if alpha_total_raw is None:
        raise ValueError("sealed.alpha_total missing")
    alpha_total = parse_decimal(str(alpha_total_raw))

    schedule_raw = sealed.get("alpha_schedule") or {}
    schedule = parse_alpha_schedule(schedule_raw)

    eval_harness_id = _require_str(sealed, "eval_harness_id")
    eval_harness_hash = _require_str(sealed, "eval_harness_hash")
    eval_suite_hash = _require_str(sealed, "eval_suite_hash")

    allowed_keys: dict[str, str] = {}
    primary_key = sealed.get("public_key")
    primary_id = sealed.get("key_id")
    if primary_key or primary_id:
        if not isinstance(primary_key, str) or not primary_key:
            raise ValueError("sealed.public_key missing")
        if not isinstance(primary_id, str) or not primary_id:
            raise ValueError("sealed.key_id missing")
        allowed_keys[primary_id] = primary_key

    allowed_keys.update(_load_key_list(sealed.get("public_keys")))
    allowed_keys.update(_load_key_list(sealed.get("prev_public_keys")))

    if require_keys and not allowed_keys:
        raise ValueError("no sealed public keys configured")

    return SealedConfig(
        alpha_total=alpha_total,
        alpha_schedule=schedule,
        eval_harness_id=eval_harness_id,
        eval_harness_hash=eval_harness_hash,
        eval_suite_hash=eval_suite_hash,
        allowed_keys=allowed_keys,
    )


def _load_key_list(raw: object) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, list):
        raise ValueError("sealed public_keys must be a list")
    out: dict[str, str] = {}
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError("sealed public_keys entries must be objects")
        key_id = entry.get("key_id")
        key = entry.get("public_key")
        if not isinstance(key_id, str) or not isinstance(key, str):
            raise ValueError("sealed public_keys entries must include key_id and public_key")
        out[key_id] = key
    return out


def _require_str(sealed: dict, label: str) -> str:
    value = sealed.get(label)
    if not isinstance(value, str) or not value:
        raise ValueError(f"sealed.{label} missing")
    return value
