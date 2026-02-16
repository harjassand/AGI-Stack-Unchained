from __future__ import annotations

from typing import Any, Dict, Tuple

from genesis.capsules.canonicalize import canonical_bytes, sha256_hex

WITNESS_CERT_TYPE = "identifiability_witness"
WITNESS_CHECKER_ID = "cdel.identifiability.v1"


def witness_hash(witness: Dict[str, Any]) -> str:
    return sha256_hex(canonical_bytes(witness))


def build_witness_certificate(witness: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "cert_type": WITNESS_CERT_TYPE,
        "payload_hash": witness_hash(witness),
        "checker_id": WITNESS_CHECKER_ID,
    }


def validate_witness_certificate(
    witness: Dict[str, Any] | None,
    certificates: list[Dict[str, Any]] | None,
) -> Tuple[bool, str | None]:
    if not isinstance(witness, dict):
        return False, "missing_identifiability_witness"
    certs = certificates or []
    payload = witness_hash(witness)
    for cert in certs:
        if cert.get("cert_type") != WITNESS_CERT_TYPE:
            continue
        if cert.get("checker_id") != WITNESS_CHECKER_ID:
            continue
        if cert.get("payload_hash") == payload:
            return True, None
    return False, "missing_identifiability_certificate"
