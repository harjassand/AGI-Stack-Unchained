"""Canonicalization and hashing for adoption payloads."""

from __future__ import annotations

from blake3 import blake3

from cdel.constraints import canonicalize_constraints_payload
from cdel.kernel.canon import canonical_json_bytes, canonicalize_spec


def canonicalize_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    concept = payload.get("concept")
    chosen_symbol = payload.get("chosen_symbol")
    baseline_symbol = payload.get("baseline_symbol")
    certificate = payload.get("certificate") or {}
    constraints = payload.get("constraints") or {}
    if not isinstance(concept, str):
        raise ValueError("concept must be a string")
    if not isinstance(chosen_symbol, str):
        raise ValueError("chosen_symbol must be a string")
    if baseline_symbol is not None and not isinstance(baseline_symbol, str):
        raise ValueError("baseline_symbol must be a string or null")
    if not isinstance(certificate, dict):
        raise ValueError("certificate must be an object")
    if not isinstance(constraints, dict):
        raise ValueError("constraints must be an object")

    cert_kind = certificate.get("kind")
    if cert_kind == "stat_cert":
        canon_cert = canonicalize_spec(certificate)
    else:
        canon_cert = certificate

    canon_constraints = canonicalize_constraints_payload(constraints)
    return {
        "concept": concept,
        "chosen_symbol": chosen_symbol,
        "baseline_symbol": baseline_symbol,
        "certificate": canon_cert,
        "constraints": canon_constraints,
    }


def payload_hash_hex(payload: dict) -> str:
    data = canonical_json_bytes(payload)
    return blake3(data).hexdigest()


def payload_bytes_and_hash(payload: dict) -> tuple[bytes, str]:
    canon = canonicalize_payload(payload)
    data = canonical_json_bytes(canon)
    return data, blake3(data).hexdigest()
