"""Family semantics helpers for RSI-4 true novelty."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .canon import canon_bytes, sha256_prefixed
from .constants import require_constants
from .family_dsl.runtime import compute_signature, instantiate_family


def _theta0_from_family(family: dict[str, Any]) -> dict[str, Any]:
    params = family.get("params_schema", [])
    if not isinstance(params, list):
        return {}
    theta0: dict[str, Any] = {}
    for param in params:
        name = param.get("name")
        if not isinstance(name, str):
            continue
        ptype = param.get("type")
        min_val = param.get("min")
        if ptype == "int":
            if isinstance(min_val, int):
                theta0[name] = int(min_val)
        elif ptype == "fixed":
            if isinstance(min_val, str):
                theta0[name] = min_val
    return theta0


@dataclass(frozen=True)
class SemanticsProbe:
    probe_key: str
    inst_hash: str
    suite_row_hash: str
    suite_row: dict[str, Any]


def _probe_keys() -> tuple[str, str, bytes, bytes]:
    constants = require_constants()
    sem = constants.get("family_semantics", {})
    key_a = sem.get("probe_key_a")
    key_b = sem.get("probe_key_b")
    if not isinstance(key_a, str) or not isinstance(key_b, str):
        raise ValueError("missing family_semantics probe keys")
    return key_a, key_b, _parse_prefixed_hash(key_a), _parse_prefixed_hash(key_b)


def _parse_prefixed_hash(value: str) -> bytes:
    hex_part = value.split(":", 1)[1] if ":" in value else value
    return bytes.fromhex(hex_part)


def _suite_row_from_instance(instance_spec: dict[str, Any]) -> dict[str, Any]:
    payload = instance_spec.get("payload")
    if isinstance(payload, dict):
        suite_row = payload.get("suite_row")
        if isinstance(suite_row, dict):
            return suite_row
    return {}


def _probe_family(family: dict[str, Any], probe_key: str, probe_bytes: bytes) -> SemanticsProbe:
    dummy_commit = {"commitment": probe_key}
    theta0 = _theta0_from_family(family)
    instance = instantiate_family(family, theta0, dummy_commit, epoch_key=probe_bytes, skip_validation=True)
    suite_row = _suite_row_from_instance(instance)
    suite_row_hash = sha256_prefixed(canon_bytes(suite_row))
    inst_hash = instance.get("inst_hash")
    if not isinstance(inst_hash, str):
        inst_hash = sha256_prefixed(canon_bytes(instance))
    return SemanticsProbe(
        probe_key=probe_key,
        inst_hash=inst_hash,
        suite_row_hash=suite_row_hash,
        suite_row=suite_row,
    )


def compute_semantic_fingerprint(family_id: str, suite_row_hash_a: str, suite_row_hash_b: str) -> str:
    payload = {
        "family_id": family_id,
        "suite_row_hash_a": suite_row_hash_a,
        "suite_row_hash_b": suite_row_hash_b,
    }
    return sha256_prefixed(canon_bytes(payload))


def build_family_semantics_report(
    *,
    epoch_id: str,
    family: dict[str, Any],
    prev_frontier_families: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    family_id = family.get("family_id")
    if not isinstance(family_id, str):
        raise ValueError("family_id missing")

    key_a, key_b, key_a_bytes, key_b_bytes = _probe_keys()
    probe_a = _probe_family(family, key_a, key_a_bytes)
    probe_b = _probe_family(family, key_b, key_b_bytes)

    env_kind = probe_a.suite_row.get("env") if isinstance(probe_a.suite_row, dict) else None
    if not isinstance(env_kind, str):
        env_kind = "unknown"

    semantic_fingerprint = compute_semantic_fingerprint(family_id, probe_a.suite_row_hash, probe_b.suite_row_hash)

    prev_frontier = prev_frontier_families or []
    prev_fingerprints: set[str] = set()
    for prev in prev_frontier:
        prev_id = prev.get("family_id")
        if not isinstance(prev_id, str):
            continue
        prev_probe_a = _probe_family(prev, key_a, key_a_bytes)
        prev_probe_b = _probe_family(prev, key_b, key_b_bytes)
        prev_fingerprints.add(
            compute_semantic_fingerprint(prev_id, prev_probe_a.suite_row_hash, prev_probe_b.suite_row_hash)
        )

    key_sensitive = probe_a.suite_row_hash != probe_b.suite_row_hash
    fingerprint_unique = semantic_fingerprint not in prev_fingerprints

    signature_match = family.get("signature") == compute_signature(family)

    report = {
        "schema": "family_semantics_report_v1",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "family_id": family_id,
        "env_kind": env_kind,
        "semantic_fingerprint": semantic_fingerprint,
        "probe": {
            "probe_key_a": key_a,
            "probe_key_b": key_b,
            "inst_hash_a": probe_a.inst_hash,
            "inst_hash_b": probe_b.inst_hash,
            "suite_row_hash_a": probe_a.suite_row_hash,
            "suite_row_hash_b": probe_b.suite_row_hash,
        },
        "checks": {
            "key_sensitive": {
                "ok": bool(key_sensitive),
                "reason_codes": [] if key_sensitive else ["FAMILY_NOT_KEY_SENSITIVE"],
            },
            "fingerprint_unique_vs_prev_frontier": {
                "ok": bool(fingerprint_unique),
                "reason_codes": [] if fingerprint_unique else ["FAMILY_SEMANTIC_FINGERPRINT_COLLISION"],
            },
            "signature_matches_recomputed": {
                "ok": bool(signature_match),
                "reason_codes": [] if signature_match else ["FAMILY_SIGNATURE_MISMATCH"],
            },
        },
    }
    return report
