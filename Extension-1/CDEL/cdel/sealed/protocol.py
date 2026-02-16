"""Canonical payloads for sealed certificates."""

from __future__ import annotations

from cdel.sealed.canon import canon_bytes


def stat_cert_signing_payload(spec: dict) -> dict:
    certificate = spec.get("certificate") or {}
    cert_payload = {k: v for k, v in certificate.items() if k != "signature"}
    return {
        "kind": "stat_cert",
        "concept": spec.get("concept"),
        "metric": spec.get("metric"),
        "null": spec.get("null"),
        "baseline_symbol": spec.get("baseline_symbol"),
        "candidate_symbol": spec.get("candidate_symbol"),
        "eval": spec.get("eval"),
        "risk": spec.get("risk"),
        "certificate": cert_payload,
    }


def stat_cert_signing_bytes(spec: dict) -> bytes:
    return canon_bytes(stat_cert_signing_payload(spec))
