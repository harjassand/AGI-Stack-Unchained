"""Trace hash-chain primitive for omega daemon."""

from __future__ import annotations

from typing import Any

from .omega_common_v1 import canon_hash_obj, ensure_sha256, validate_schema, write_hashed_json


def compute_h0(
    *,
    run_seed_u64: int,
    pack_hash: str,
    policy_hash: str,
    registry_hash: str,
    objectives_hash: str,
    tick_u64: int,
    prev_state_hash: str,
) -> str:
    return canon_hash_obj(
        {
            "schema_version": "omega_trace_seed_v1",
            "run_seed_u64": int(run_seed_u64),
            "pack_hash": pack_hash,
            "policy_hash": policy_hash,
            "registry_hash": registry_hash,
            "objectives_hash": objectives_hash,
            "tick_u64": int(tick_u64),
            "prev_state_hash": prev_state_hash,
        }
    )


def recompute_head(h0: str, artifact_hashes: list[str]) -> str:
    head = ensure_sha256(h0)
    for row in artifact_hashes:
        ensure_sha256(row)
        head = canon_hash_obj({"schema_version": "omega_trace_step_v1", "prev": head, "artifact_hash": row})
    return head


def build_trace_chain(
    *,
    h0: str,
    artifact_hashes: list[str],
) -> dict[str, Any]:
    payload = {
        "schema_version": "omega_trace_hash_chain_v1",
        "H0": h0,
        "artifact_hashes": artifact_hashes,
        "H_final": recompute_head(h0, artifact_hashes),
    }
    validate_schema(payload, "omega_trace_hash_chain_v1")
    return payload


def write_trace_chain(out_dir, payload: dict[str, Any]):
    return write_hashed_json(out_dir, "omega_trace_hash_chain_v1.json", payload)


__all__ = ["build_trace_chain", "compute_h0", "recompute_head", "write_trace_chain"]
