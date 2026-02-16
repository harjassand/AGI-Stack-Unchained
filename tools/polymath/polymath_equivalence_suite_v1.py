#!/usr/bin/env python3
"""Equivalence checks for polymath verifier/kernel candidates (v1)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    _value = str(_entry)
    if _value not in sys.path:
        sys.path.insert(0, _value)

from cdel.v1_7r.canon import write_canon_json
from cdel.v18_0.omega_common_v1 import canon_hash_obj, load_canon_dict, validate_schema
from cdel.v18_0.polymath_verifier_kernel_v1 import verify_domain


def _task_predictions(payload: dict[str, Any]) -> dict[str, list[Any]]:
    rows = payload.get("task_outputs")
    if not isinstance(rows, list):
        raise RuntimeError("SCHEMA_FAIL")
    out: dict[str, list[Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise RuntimeError("SCHEMA_FAIL")
        task_id = str(row.get("task_id", "")).strip()
        preds = row.get("predictions")
        if not task_id or not isinstance(preds, list):
            raise RuntimeError("SCHEMA_FAIL")
        out[task_id] = list(preds)
    return out


def run_equivalence(
    *,
    state_dir: Path,
    domain_pack_path: Path,
    reference_outputs_path: Path,
    candidate_outputs_path: Path,
    out_path: Path,
) -> dict[str, Any]:
    if verify_domain(state_dir=state_dir, domain_pack_path=domain_pack_path, candidate_outputs_path=reference_outputs_path) != "VALID":
        raise RuntimeError("VERIFY_ERROR")
    if verify_domain(state_dir=state_dir, domain_pack_path=domain_pack_path, candidate_outputs_path=candidate_outputs_path) != "VALID":
        raise RuntimeError("VERIFY_ERROR")

    ref_payload = load_canon_dict(reference_outputs_path)
    cand_payload = load_canon_dict(candidate_outputs_path)
    ref_tasks = _task_predictions(ref_payload)
    cand_tasks = _task_predictions(cand_payload)

    cases_u64 = 0
    mismatches_u64 = 0
    for task_id in sorted(set(ref_tasks.keys()) | set(cand_tasks.keys())):
        ref = ref_tasks.get(task_id, [])
        cand = cand_tasks.get(task_id, [])
        max_len = max(len(ref), len(cand))
        cases_u64 += max_len
        for idx in range(max_len):
            ref_val = ref[idx] if idx < len(ref) else None
            cand_val = cand[idx] if idx < len(cand) else None
            if ref_val != cand_val:
                mismatches_u64 += 1

    report = {
        "candidate_hash": canon_hash_obj(cand_payload),
        "cases_u64": int(cases_u64),
        "details": [],
        "domain_id": str(ref_payload.get("domain_id", "")),
        "kernel_version": "polymath_verifier_kernel_v1",
        "mismatches_u64": int(mismatches_u64),
        "pass_b": int(mismatches_u64) == 0,
        "reference_hash": canon_hash_obj(ref_payload),
        "report_id": "sha256:" + ("0" * 64),
        "schema_version": "polymath_equivalence_report_v1",
    }
    no_id = dict(report)
    no_id.pop("report_id", None)
    report["report_id"] = canon_hash_obj(no_id)
    validate_schema(report, "polymath_equivalence_report_v1")
    write_canon_json(out_path, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(prog="polymath_equivalence_suite_v1")
    parser.add_argument("--state_dir", required=True)
    parser.add_argument("--domain_pack", required=True)
    parser.add_argument("--reference_outputs", required=True)
    parser.add_argument("--candidate_outputs", required=True)
    parser.add_argument("--out_path", required=True)
    args = parser.parse_args()

    report = run_equivalence(
        state_dir=Path(args.state_dir).resolve(),
        domain_pack_path=Path(args.domain_pack).resolve(),
        reference_outputs_path=Path(args.reference_outputs).resolve(),
        candidate_outputs_path=Path(args.candidate_outputs).resolve(),
        out_path=Path(args.out_path).resolve(),
    )
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
