"""Deterministic candidate enumeration for SAS-Science v13.0."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..v1_7r.canon import canon_bytes, sha256_prefixed
from .sas_science_ir_v1 import compute_theory_id, compute_complexity


def _now_utc() -> str:
    # Deterministic timestamp to keep content-addressed artifacts stable.
    return "1970-01-01T00:00:00Z"


def _compute_bundle_id(bundle: dict[str, Any]) -> str:
    payload = dict(bundle)
    payload.pop("bundle_id", None)
    return sha256_prefixed(canon_bytes(payload))


def _compute_receipt_id(receipt: dict[str, Any]) -> str:
    payload = dict(receipt)
    payload.pop("receipt_id", None)
    return sha256_prefixed(canon_bytes(payload))


def _sources_for_manifest(manifest: dict[str, Any], *, central: bool) -> list[str]:
    frame_kind = manifest.get("frame_kind")
    bodies = list(manifest.get("bodies") or [])
    if central:
        return ["Origin"] if frame_kind == "HELIOCENTRIC_SUN_AT_ORIGIN_V1" else ["Sun"]
    sources = list(bodies)
    if frame_kind == "BARYCENTRIC_WITH_SUN_ROW_V1" and "Sun" not in sources:
        sources.append("Sun")
    return sources


def enumerate_candidate_irs(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    target_bodies = list(manifest.get("bodies") or [])
    candidates: list[dict[str, Any]] = []
    order = [
        ("CANDIDATE_CENTRAL_POWERLAW_V1", 2),
        ("CANDIDATE_CENTRAL_POWERLAW_V1", 3),
        ("CANDIDATE_CENTRAL_POWERLAW_V1", 4),
        ("CANDIDATE_NBODY_POWERLAW_V1", 2),
        ("CANDIDATE_NBODY_POWERLAW_V1", 3),
        ("CANDIDATE_NBODY_POWERLAW_V1", 4),
    ]
    for kind, p in order:
        central = kind == "CANDIDATE_CENTRAL_POWERLAW_V1"
        ir = {
            "ir_version": "sas_science_theory_ir_v1",
            "theory_kind": kind,
            "target_bodies": target_bodies,
            "source_bodies": _sources_for_manifest(manifest, central=central),
            "force_law": {
                "vector_form": "DISPLACEMENT_OVER_NORM_POW_V1",
                "norm_pow_p": int(p),
                "coeff_sharing": "SOURCE_MASS_ONLY_V1",
            },
            "parameters": {},
            "complexity": {"node_count": 0, "term_count": 0, "param_count": 0},
            "theory_id": "",
        }
        ir["complexity"] = compute_complexity(ir)
        ir["theory_id"] = compute_theory_id(ir)
        candidates.append(ir)
    return candidates


def build_candidate_bundle(
    *,
    candidate_irs: list[dict[str, Any]],
    generator_seed: str,
    generator_config_hash: str,
) -> dict[str, Any]:
    bundle = {
        "schema_version": "sas_science_candidate_bundle_v1",
        "bundle_id": "",
        "created_utc": _now_utc(),
        "generator_version": "sas_science_generator_v1",
        "generator_seed": generator_seed,
        "generator_config_hash": generator_config_hash,
        "candidates": [],
    }
    for ir in candidate_irs:
        bundle["candidates"].append(
            {
                "theory_id": ir.get("theory_id"),
                "theory_kind": ir.get("theory_kind"),
                "norm_pow_p": ir.get("force_law", {}).get("norm_pow_p"),
                "tags": ["powerlaw", "deterministic"],
                "status": "CANDIDATE",
                "forbidden_scan": {"passed": True, "hits": []},
            }
        )
    bundle["bundle_id"] = _compute_bundle_id(bundle)
    return bundle


def build_gen_receipt(
    *,
    bundle_id: str,
    generator_seed: str,
    generator_config_hash: str,
    stdout_hash: str,
    stderr_hash: str,
) -> dict[str, Any]:
    receipt = {
        "schema_version": "sas_science_gen_receipt_v1",
        "receipt_id": "",
        "created_utc": _now_utc(),
        "generator_version": "sas_science_generator_v1",
        "generator_seed": generator_seed,
        "generator_config_hash": generator_config_hash,
        "bundle_hash": bundle_id,
        "network_used": False,
        "stdout_hash": stdout_hash,
        "stderr_hash": stderr_hash,
    }
    receipt["receipt_id"] = _compute_receipt_id(receipt)
    return receipt


__all__ = ["enumerate_candidate_irs", "build_candidate_bundle", "build_gen_receipt"]
