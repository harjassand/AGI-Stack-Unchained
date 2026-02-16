"""Omega test-plan receipt helpers (v1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..v1_7r.canon import write_canon_json
from .omega_common_v1 import canon_hash_obj, ensure_sha256, fail, load_canon_dict, require_relpath, validate_schema, write_hashed_json

_RECEIPT_GLOB = "sha256_*.omega_test_plan_receipt_v1.json"
_REQUIRED_CAMPAIGN_IDS = {
    "rsi_omega_self_optimize_core_v1",
    "rsi_omega_apply_shadow_proposal_v1",
    "rsi_polymath_scout_v1",
    "rsi_polymath_bootstrap_domain_v1",
    "rsi_polymath_conquer_domain_v1",
}


def campaign_requires_test_plan_receipt(campaign_id: str) -> bool:
    value = str(campaign_id).strip()
    return value in _REQUIRED_CAMPAIGN_IDS or value.startswith("rsi_domain_")


def _normalized_touched_paths(rows: list[str]) -> list[str]:
    out: set[str] = set()
    for row in rows:
        out.add(require_relpath(str(row)))
    return sorted(out)


def _inputs_hash(*, touched_paths: list[str], plan_id: str, test_files: list[str], repo_tree_hash: str) -> str:
    return canon_hash_obj(
        {
            "touched_paths": _normalized_touched_paths(touched_paths),
            "plan_id": str(plan_id),
            "test_files": sorted(set(str(value) for value in test_files if str(value))),
            "repo_tree_hash": str(repo_tree_hash),
        }
    )


def validate_test_plan_receipt(*, payload: dict[str, Any], touched_paths: list[str]) -> None:
    validate_schema(payload, "omega_test_plan_receipt_v1")
    if str(payload.get("result", "")) != "PASS":
        fail("TEST_PLAN_RECEIPT_MISSING_OR_FAIL")

    tests_run = payload.get("tests_run")
    durations = payload.get("durations_ms")
    test_files = payload.get("test_files")
    if not isinstance(tests_run, list) or not isinstance(durations, list) or not isinstance(test_files, list):
        fail("SCHEMA_FAIL")
    if len(tests_run) != len(durations):
        fail("SCHEMA_FAIL")

    receipt_touched = payload.get("touched_paths")
    if not isinstance(receipt_touched, list):
        fail("SCHEMA_FAIL")
    if _normalized_touched_paths([str(row) for row in receipt_touched]) != _normalized_touched_paths(touched_paths):
        fail("TEST_PLAN_RECEIPT_MISSING_OR_FAIL")

    plan_id = str(payload.get("plan_id", "")).strip()
    repo_tree_hash = ensure_sha256(payload.get("repo_tree_hash"))
    expected_inputs_hash = _inputs_hash(
        touched_paths=touched_paths,
        plan_id=plan_id,
        test_files=[str(row) for row in test_files],
        repo_tree_hash=repo_tree_hash,
    )
    if str(payload.get("inputs_hash", "")) != expected_inputs_hash:
        fail("TEST_PLAN_RECEIPT_MISSING_OR_FAIL")


def emit_test_plan_receipt(*, promotion_dir: Path, touched_paths: list[str], mode: str = "promotion") -> tuple[dict[str, Any], dict[str, Any]]:
    from tools.omega.omega_test_router_v1 import build_test_plan_receipt, route_and_run

    report = route_and_run(touched_paths=_normalized_touched_paths(touched_paths), mode=str(mode))
    report_path = promotion_dir / "OMEGA_TEST_ROUTER_REPORT_v1.json"
    write_canon_json(report_path, report)

    receipt_payload = build_test_plan_receipt(report=report, touched_paths=_normalized_touched_paths(touched_paths))
    validate_test_plan_receipt(payload=receipt_payload, touched_paths=touched_paths)
    _, receipt_obj, _ = write_hashed_json(
        promotion_dir,
        "omega_test_plan_receipt_v1.json",
        receipt_payload,
        id_field="receipt_id",
    )
    write_canon_json(promotion_dir / "omega_test_plan_receipt_v1.json", receipt_obj)
    return report, receipt_obj


def load_test_plan_receipt(*, promotion_dir: Path, touched_paths: list[str], required: bool) -> dict[str, Any] | None:
    rows = sorted(promotion_dir.glob(_RECEIPT_GLOB), key=lambda row: row.as_posix())
    if not rows:
        if required:
            fail("TEST_PLAN_RECEIPT_MISSING_OR_FAIL")
        return None
    receipt_path = rows[-1]
    payload = load_canon_dict(receipt_path)
    digest = canon_hash_obj(payload)
    expected_digest = "sha256:" + receipt_path.name[len("sha256_") : len("sha256_") + 64]
    if digest != expected_digest:
        fail("TEST_PLAN_RECEIPT_MISSING_OR_FAIL")

    plain_path = promotion_dir / "omega_test_plan_receipt_v1.json"
    if plain_path.exists() and plain_path.is_file():
        plain_payload = load_canon_dict(plain_path)
        if canon_hash_obj(plain_payload) != digest:
            fail("TEST_PLAN_RECEIPT_MISSING_OR_FAIL")

    validate_test_plan_receipt(payload=payload, touched_paths=touched_paths)
    return payload


__all__ = [
    "campaign_requires_test_plan_receipt",
    "emit_test_plan_receipt",
    "load_test_plan_receipt",
    "validate_test_plan_receipt",
]
