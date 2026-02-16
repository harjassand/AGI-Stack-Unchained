#!/usr/bin/env python3
"""SH-1 behavior signature and novelty helpers."""

from __future__ import annotations

import hashlib
from typing import Any, Iterable, Sequence

from cdel.v1_7r.canon import canon_bytes


def _invalid(reason: str) -> RuntimeError:
    msg = reason
    if not msg.startswith("INVALID:"):
        msg = f"INVALID:{msg}"
    return RuntimeError(msg)


def _sha256_prefixed(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _thresholds_from_config(ge_config: dict[str, Any]) -> list[int]:
    proposal = ge_config.get("proposal_space_patch")
    if not isinstance(proposal, dict):
        raise _invalid("SCHEMA_FAIL")
    rows = proposal.get("size_buckets_bytes_u64")
    if not isinstance(rows, list) or not rows:
        raise _invalid("SCHEMA_FAIL")
    out: list[int] = []
    for row in rows:
        value = int(row)
        if value <= 0:
            raise _invalid("SCHEMA_FAIL")
        out.append(value)
    return out


def _bucket_u8(value_u64: int, thresholds: list[int]) -> int:
    value = max(0, int(value_u64))
    for idx, threshold in enumerate(thresholds):
        if value <= int(threshold):
            return int(idx)
    return int(len(thresholds))


def refutation_code_hash16(refutation_code: str) -> int:
    code = str(refutation_code).strip()
    if not code:
        return 0
    digest = hashlib.sha256(code.encode("utf-8")).digest()
    return int.from_bytes(digest[:2], "big", signed=False)


def _decision_phi(receipt_payload: dict[str, Any]) -> int:
    return 1 if str(receipt_payload.get("decision", "")).strip() == "PROMOTE" else 0


def _eval_status_phi(receipt_payload: dict[str, Any]) -> int:
    status = str(receipt_payload.get("eval_status", "")).strip()
    if status == "PASS":
        return 1
    if status == "FAIL":
        return 0
    if status == "REFUTED":
        return -1
    raise _invalid("SCHEMA_FAIL")


def _determinism_phi(receipt_payload: dict[str, Any]) -> int:
    status = str(receipt_payload.get("determinism_check", "")).strip()
    if status == "PASS":
        return 1
    if status == "DIVERGED":
        return -1
    if status == "REFUTED":
        return -2
    raise _invalid("SCHEMA_FAIL")


def sentinel_class_value(
    *,
    ge_config: dict[str, Any],
    receipt_payload: dict[str, Any],
    refutation_code: str,
) -> int:
    mapping = ge_config.get("sentinel_mapping")
    if not isinstance(mapping, dict):
        raise _invalid("SCHEMA_FAIL")

    code = str(refutation_code).strip()
    busy = {str(row).strip() for row in (mapping.get("BUSY_FAIL") or [])}
    logic = {str(row).strip() for row in (mapping.get("LOGIC_FAIL") or [])}
    safety = {str(row).strip() for row in (mapping.get("SAFETY_FAIL") or [])}

    if code in busy:
        return 1
    if code in logic:
        return 2
    if code in safety:
        return 3

    if code:
        return 2

    det = str(receipt_payload.get("determinism_check", "")).strip()
    if det == "DIVERGED":
        return 3
    return 0


def phi_vector(
    *,
    ge_config: dict[str, Any],
    receipt_payload: dict[str, Any],
    refutation_code: str,
) -> list[int]:
    cost = receipt_payload.get("cost_vector")
    if not isinstance(cost, dict):
        raise _invalid("SCHEMA_FAIL")
    thresholds = _thresholds_from_config(ge_config)

    phi = [
        _decision_phi(receipt_payload),
        _eval_status_phi(receipt_payload),
        _determinism_phi(receipt_payload),
        sentinel_class_value(
            ge_config=ge_config,
            receipt_payload=receipt_payload,
            refutation_code=refutation_code,
        ),
        _bucket_u8(int(cost.get("cpu_ms", 0)), thresholds),
        _bucket_u8(int(cost.get("wall_ms", 0)), thresholds),
        refutation_code_hash16(refutation_code),
        0,
    ]
    return [int(row) for row in phi]


def build_behavior_signature(
    *,
    ge_config: dict[str, Any],
    receipt_payload: dict[str, Any],
    refutation_code: str,
) -> dict[str, Any]:
    if str(receipt_payload.get("schema_version", "")).strip() != "ccap_receipt_v1":
        raise _invalid("SCHEMA_FAIL")
    phi = phi_vector(
        ge_config=ge_config,
        receipt_payload=receipt_payload,
        refutation_code=refutation_code,
    )
    beh_id = _sha256_prefixed(canon_bytes({"phi": phi}))
    return {
        "schema_version": "ge_behavior_sig_v1",
        "beh_id": beh_id,
        "phi": phi,
    }


def _digest_bytes(sha256_value: str) -> bytes:
    value = str(sha256_value).strip()
    if not value.startswith("sha256:"):
        raise _invalid("SCHEMA_FAIL")
    hexd = value.split(":", 1)[1]
    if len(hexd) != 64:
        raise _invalid("SCHEMA_FAIL")
    return bytes.fromhex(hexd)


def hamming_distance_bits(a_sha256: str, b_sha256: str) -> int:
    a = _digest_bytes(a_sha256)
    b = _digest_bytes(b_sha256)
    return int(sum((x ^ y).bit_count() for x, y in zip(a, b, strict=True)))


def novelty_bits(*, beh_id: str, reservoir_beh_ids: Sequence[str]) -> int:
    if not reservoir_beh_ids:
        return 256
    return min(hamming_distance_bits(beh_id, prior) for prior in reservoir_beh_ids)


def novelty_series(
    *,
    beh_ids: Iterable[str],
    reservoir_size_u64: int,
) -> list[int]:
    reservoir_size = max(1, int(reservoir_size_u64))
    reservoir: list[str] = []
    out: list[int] = []
    for beh_id in beh_ids:
        current_reservoir = reservoir[-reservoir_size:]
        out.append(int(novelty_bits(beh_id=beh_id, reservoir_beh_ids=current_reservoir)))
        reservoir.append(str(beh_id))
    return out


__all__ = [
    "build_behavior_signature",
    "hamming_distance_bits",
    "novelty_bits",
    "novelty_series",
    "phi_vector",
    "refutation_code_hash16",
    "sentinel_class_value",
]
