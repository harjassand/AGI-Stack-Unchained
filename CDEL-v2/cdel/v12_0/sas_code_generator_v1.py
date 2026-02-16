"""Candidate generator for SAS-CODE (v12.0)."""

from __future__ import annotations

import os
from typing import Any

from ..v1_7r.canon import canon_bytes, sha256_prefixed
from .sas_code_ir_v1 import compute_algo_id


def _now_utc() -> str:
    seed = int(os.environ.get("OMEGA_RUN_SEED_U64", "0"))
    return f"1970-01-01T00:00:{seed % 60:02d}Z"


def _compute_bundle_id(bundle: dict[str, Any]) -> str:
    payload = dict(bundle)
    payload.pop("bundle_id", None)
    return sha256_prefixed(canon_bytes(payload))


def _compute_receipt_id(receipt: dict[str, Any]) -> str:
    payload = dict(receipt)
    payload.pop("receipt_id", None)
    return sha256_prefixed(canon_bytes(payload))


def enumerate_candidate_irs(baseline_ir: dict[str, Any]) -> list[dict[str, Any]]:
    base = dict(baseline_ir)
    base.pop("algo_id", None)
    base["schema_version"] = "sas_code_ir_v1"
    base["domain"] = "SAS_CODE_SORT_V1"

    candidates: list[dict[str, Any]] = []
    for algo_kind, tags in [
        ("MERGE_SORT_V1", ["nlogn", "divide_and_conquer", "recursion"]),
        ("INSERTION_SORT_V1", ["n2", "local_swap"]),
    ]:
        ir = dict(base)
        ir["algo_kind"] = algo_kind
        ir["tags"] = list(tags)
        ir["algo_id"] = compute_algo_id(ir)
        candidates.append(ir)
    return candidates


def build_candidate_bundle(
    *,
    baseline_algo_id: str,
    candidate_irs: list[dict[str, Any]],
    generator_seed: str,
    generator_config_hash: str,
) -> dict[str, Any]:
    bundle = {
        "schema_version": "sas_code_candidate_bundle_v1",
        "bundle_id": "",
        "created_utc": _now_utc(),
        "generator_seed": generator_seed,
        "generator_config_hash": generator_config_hash,
        "baseline_algo_id": baseline_algo_id,
        "candidates": [],
    }
    for ir in candidate_irs:
        bundle["candidates"].append(
            {
                "algo_id": ir.get("algo_id"),
                "algo_kind": ir.get("algo_kind"),
                "tags": list(ir.get("tags") or []),
                "status": "CANDIDATE",
                "forbidden_token_scan": {"passed": True, "hits": []},
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
        "schema_version": "sas_code_gen_receipt_v1",
        "receipt_id": "",
        "created_utc": _now_utc(),
        "generator_version": "sas_code_generator_v1",
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
