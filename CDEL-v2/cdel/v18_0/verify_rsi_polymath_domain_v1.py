"""Fail-closed verifier for polymath bootstrap/conquer campaigns."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .omega_common_v1 import OmegaV18Error, fail, load_canon_dict, validate_schema
from .polymath_verifier_kernel_v1 import verify_domain


def _resolve_state(path: Path) -> Path:
    root = path.resolve()
    candidates = [
        root / "daemon" / "rsi_polymath_bootstrap_domain_v1" / "state",
        root / "daemon" / "rsi_polymath_conquer_domain_v1" / "state",
        root,
    ]
    for candidate in candidates:
        if (candidate / "reports").exists() and (candidate / "reports").is_dir():
            return candidate
    fail("SCHEMA_FAIL")
    return root


def _metric_improved(metric_id: str, baseline_q32: int, improved_q32: int) -> bool:
    if metric_id in {"rmse", "logloss"}:
        return int(improved_q32) < int(baseline_q32)
    return int(improved_q32) > int(baseline_q32)


def _subrun_root(state_root: Path) -> Path:
    # state_root == <subrun>/daemon/<campaign_id>/state
    return state_root.parents[2]


def _verify_bootstrap(state_root: Path, report: dict[str, Any]) -> str:
    status = str(report.get("status", "")).strip()
    if status in {"BLOCKED_POLICY", "BLOCKED_LICENSE", "BLOCKED_SIZE", "NO_CANDIDATE"}:
        return "VALID"

    domain_pack_rel = str(report.get("domain_pack_rel", "")).strip()
    candidate_outputs_rel = str(report.get("candidate_outputs_rel", "")).strip()
    equiv_rel = str(report.get("equivalence_report_rel", "")).strip()
    if not domain_pack_rel or not candidate_outputs_rel or not equiv_rel:
        fail("SCHEMA_FAIL")

    subrun_root = _subrun_root(state_root)
    domain_pack_path = (subrun_root / domain_pack_rel).resolve()
    candidate_outputs_path = (subrun_root / candidate_outputs_rel).resolve()
    if verify_domain(state_dir=state_root, domain_pack_path=domain_pack_path, candidate_outputs_path=candidate_outputs_path) != "VALID":
        fail("VERIFY_ERROR")

    equiv_path = (subrun_root / equiv_rel).resolve()
    equiv = load_canon_dict(equiv_path)
    validate_schema(equiv, "polymath_equivalence_report_v1")
    if not bool(equiv.get("pass_b", False)):
        fail("VERIFY_ERROR")
    return "VALID"


def _verify_conquer(state_root: Path, report: dict[str, Any]) -> str:
    status = str(report.get("status", "")).strip()
    if status in {"NO_ACTIVE_DOMAIN", "NO_READY_DOMAIN"}:
        return "VALID"

    domain_pack_rel = str(report.get("domain_pack_rel", "")).strip()
    baseline_outputs_rel = str(report.get("baseline_outputs_rel", "")).strip()
    improved_outputs_rel = str(report.get("improved_outputs_rel", "")).strip()
    metric_id = str(report.get("metric_id", "")).strip()
    baseline_q32 = int(report.get("baseline_metric_q32", 0))
    improved_q32 = int(report.get("improved_metric_q32", 0))
    if not all([domain_pack_rel, baseline_outputs_rel, improved_outputs_rel, metric_id]):
        fail("SCHEMA_FAIL")

    subrun_root = _subrun_root(state_root)
    domain_pack_path = (subrun_root / domain_pack_rel).resolve()
    baseline_outputs_path = (subrun_root / baseline_outputs_rel).resolve()
    improved_outputs_path = (subrun_root / improved_outputs_rel).resolve()

    if verify_domain(state_dir=state_root, domain_pack_path=domain_pack_path, candidate_outputs_path=baseline_outputs_path) != "VALID":
        fail("VERIFY_ERROR")
    if verify_domain(state_dir=state_root, domain_pack_path=domain_pack_path, candidate_outputs_path=improved_outputs_path) != "VALID":
        fail("VERIFY_ERROR")

    if not _metric_improved(metric_id=metric_id, baseline_q32=baseline_q32, improved_q32=improved_q32):
        fail("VERIFY_ERROR")
    return "VALID"


def verify(state_dir: Path, *, mode: str = "full") -> str:
    if mode != "full":
        fail("MODE_UNSUPPORTED")
    state_root = _resolve_state(state_dir)

    bootstrap_report = state_root / "reports" / "polymath_bootstrap_report_v1.json"
    conquer_report = state_root / "reports" / "polymath_conquer_report_v1.json"

    if bootstrap_report.exists() and bootstrap_report.is_file():
        report = load_canon_dict(bootstrap_report)
        if str(report.get("schema_version", "")) != "polymath_bootstrap_report_v1":
            fail("SCHEMA_FAIL")
        return _verify_bootstrap(state_root, report)

    if conquer_report.exists() and conquer_report.is_file():
        report = load_canon_dict(conquer_report)
        if str(report.get("schema_version", "")) != "polymath_conquer_report_v1":
            fail("SCHEMA_FAIL")
        return _verify_conquer(state_root, report)

    fail("MISSING_STATE_INPUT")
    return "VALID"


def main() -> None:
    parser = argparse.ArgumentParser(prog="verify_rsi_polymath_domain_v1")
    parser.add_argument("--mode", required=True)
    parser.add_argument("--state_dir", required=True)
    args = parser.parse_args()

    try:
        print(verify(Path(args.state_dir), mode=str(args.mode)))
    except OmegaV18Error as exc:
        msg = str(exc)
        if not msg.startswith("INVALID:"):
            msg = f"INVALID:{msg}"
        print(msg)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
