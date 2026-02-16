"""Apply best shadow proposal into a promotable Omega bundle (v1)."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..v1_7r.canon import write_canon_json
from .omega_common_v1 import canon_hash_obj, fail, load_canon_dict, repo_root, require_relpath, write_hashed_json
from .omega_test_plan_v1 import emit_test_plan_receipt


_ALLOWED_PATCH_PREFIXES: tuple[str, ...] = (
    "orchestrator/omega_v18_0/",
    "CDEL-v2/cdel/v18_0/",
    "tools/omega/",
    "Genesis/schema/v18_0/",
)
_FORBIDDEN_PATCH_PREFIXES: tuple[str, ...] = (
    "meta-core/engine/",
    "meta-core/kernel/",
    "meta-core/meta_constitution/",
    "CDEL-v2/cdel/v18_0/verify_rsi_",
)
_GATE_STATUS_RE = re.compile(r"- Gate ([A-Z]).*\\*\\*(PASS|FAIL|SKIP)\\*\\*")


def _load_pack(path: Path) -> dict[str, Any]:
    payload = load_canon_dict(path)
    if str(payload.get("schema_version", "")).strip() != "rsi_omega_apply_shadow_proposal_pack_v1":
        fail("SCHEMA_FAIL")
    return payload


def _proposal_rows(root: Path, proposals_glob: str) -> list[tuple[Path, dict[str, Any]]]:
    out: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(root.glob(proposals_glob), key=lambda row: row.as_posix()):
        payload = load_canon_dict(path)
        if str(payload.get("schema_version", "")).strip() != "omega_shadow_proposal_v1":
            continue
        out.append((path, payload))
    return out


def _proposal_tests_pass(payload: dict[str, Any]) -> bool:
    tests = payload.get("tests")
    if not isinstance(tests, list):
        return False
    if not tests:
        return False
    return all(isinstance(row, dict) and bool(row.get("pass_b", row.get("pass", False))) for row in tests)


def _path_allowed(path_rel: str) -> bool:
    value = require_relpath(path_rel)
    if any(value.startswith(prefix) for prefix in _FORBIDDEN_PATCH_PREFIXES):
        return False
    return any(value.startswith(prefix) for prefix in _ALLOWED_PATCH_PREFIXES)


def _touched_paths_from_proposal(payload: dict[str, Any]) -> list[str]:
    rows = payload.get("touched_paths")
    if not isinstance(rows, list):
        return []
    out: list[str] = []
    for row in rows:
        if not isinstance(row, str):
            continue
        path_rel = require_relpath(row)
        if _path_allowed(path_rel):
            out.append(path_rel)
    return sorted(set(out))


def _proposal_sort_key(row: tuple[Path, dict[str, Any]]) -> tuple[int, str]:
    _path, payload = row
    return (-max(0, int(payload.get("expected_stps_delta_q32", 0))), str(payload.get("proposal_id", "")))


def _run_cmd(cmd: list[str], *, cwd: Path) -> dict[str, Any]:
    run = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "cmd": cmd,
        "return_code": int(run.returncode),
        "pass_b": int(run.returncode) == 0,
        "stdout_tail": "\n".join(run.stdout.splitlines()[-40:]),
        "stderr_tail": "\n".join(run.stderr.splitlines()[-40:]),
    }


def _extract_gate_statuses(summary_path: Path) -> dict[str, str]:
    if not summary_path.exists() or not summary_path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in summary_path.read_text(encoding="utf-8").splitlines():
        match = _GATE_STATUS_RE.search(line)
        if not match:
            continue
        out[str(match.group(1))] = str(match.group(2))
    return out


def _benchmark_eval(*, root: Path, runs_root: Path, series_prefix: str) -> dict[str, Any]:
    runs_root = runs_root.resolve()
    run_dir = runs_root / series_prefix
    shutil.rmtree(run_dir, ignore_errors=True)
    cmd = [
        sys.executable,
        str(root / "tools" / "omega" / "omega_benchmark_suite_v1.py"),
        "--ticks",
        "50",
        "--series_prefix",
        series_prefix,
        "--runs_root",
        str(runs_root),
    ]
    bench = _run_cmd(cmd, cwd=root)

    summary_path = run_dir / "OMEGA_BENCHMARK_SUMMARY_v1.md"
    scorecard_path = run_dir / "OMEGA_RUN_SCORECARD_v1.json"
    timings_path = run_dir / "OMEGA_TIMINGS_AGG_v1.json"
    gate_status = _extract_gate_statuses(summary_path)
    stps_non_noop_q32 = 0
    dispatch_ns_median_u64 = 0
    subverify_ns_median_u64 = 0
    if scorecard_path.exists() and scorecard_path.is_file():
        scorecard = load_canon_dict(scorecard_path)
        stps_non_noop_q32 = max(0, int(scorecard.get("median_stps_non_noop_q32", 0)))
    if timings_path.exists() and timings_path.is_file():
        timings = load_canon_dict(timings_path)
        run_bucket = (timings.get("action_buckets") or {}).get("RUN_*", {})
        stage_ns = (run_bucket or {}).get("stage_ns", {})
        dispatch_ns_median_u64 = max(0, int(float(((stage_ns.get("dispatch_campaign") or {}).get("median_ns", 0.0)))))
        subverify_ns_median_u64 = max(0, int(float(((stage_ns.get("run_subverifier") or {}).get("median_ns", 0.0)))))
    return {
        "bench": bench,
        "summary_path": summary_path.as_posix(),
        "gate_status": gate_status,
        "stps_non_noop_q32": int(stps_non_noop_q32),
        "dispatch_ns_median_u64": int(dispatch_ns_median_u64),
        "subverify_ns_median_u64": int(subverify_ns_median_u64),
    }


def _improvement_pass(*, before: dict[str, Any], after: dict[str, Any]) -> bool:
    stps_before = max(0, int(before.get("stps_non_noop_q32", 0)))
    stps_after = max(0, int(after.get("stps_non_noop_q32", 0)))
    if stps_before <= 0:
        stps_improved = stps_after > 0
    else:
        stps_improved = int(stps_after) * 100 >= int(stps_before) * 110

    dispatch_before = max(0, int(before.get("dispatch_ns_median_u64", 0)))
    dispatch_after = max(0, int(after.get("dispatch_ns_median_u64", 0)))
    subverify_before = max(0, int(before.get("subverify_ns_median_u64", 0)))
    subverify_after = max(0, int(after.get("subverify_ns_median_u64", 0)))
    dispatch_improved = dispatch_before > 0 and int(dispatch_after) * 100 <= int(dispatch_before) * 85
    subverify_improved = subverify_before > 0 and int(subverify_after) * 100 <= int(subverify_before) * 85
    return bool(stps_improved or dispatch_improved or subverify_improved)


def _run_full_self_opt_suite(*, root: Path, before_metrics: dict[str, Any], runs_root: Path) -> dict[str, Any]:
    runs_root = runs_root.resolve()
    shutil.rmtree(runs_root, ignore_errors=True)
    runs_root.mkdir(parents=True, exist_ok=True)

    tests: list[dict[str, Any]] = []
    tests.append(
        _run_cmd(
            [sys.executable, "-m", "pytest", "CDEL-v2/cdel/v18_0/tests_omega_daemon", "-q"],
            cwd=root,
        )
    )
    tests.append(
        _run_cmd(
            [sys.executable, "-m", "pytest", "CDEL-v2/cdel/v18_0/tests_omega_daemon/test_tick_determinism.py", "-q"],
            cwd=root,
        )
    )
    after_metrics = _benchmark_eval(
        root=root,
        runs_root=runs_root,
        series_prefix="coreopt_eval_after",
    )
    tests.append(dict(after_metrics["bench"]))

    gate_status = dict(after_metrics.get("gate_status") or {})
    gates_ok = gate_status.get("A") == "PASS" and gate_status.get("B") == "PASS" and gate_status.get("D") == "PASS"
    improvement_ok = _improvement_pass(before=before_metrics, after=after_metrics)
    suite_ok = all(bool(row.get("pass_b", False)) for row in tests) and gates_ok and improvement_ok
    return {
        "suite_pass_b": bool(suite_ok),
        "tests": tests,
        "before_metrics": before_metrics,
        "after_metrics": after_metrics,
        "improvement_pass_b": bool(improvement_ok),
        "gate_status": gate_status,
        "summary_path": str(after_metrics.get("summary_path", "")),
    }


def _resolve_patch_path(*, root: Path, payload: dict[str, Any], proposal_path: Path) -> Path:
    patch_value = str(payload.get("patch_path", "")).strip()
    if patch_value:
        candidate = Path(patch_value)
        candidates: list[Path] = []
        if candidate.is_absolute():
            candidates.append(candidate)
        else:
            candidates.append((root / candidate).resolve())
            candidates.append((root / "runs" / candidate).resolve())
        for row in candidates:
            if row.exists() and row.is_file():
                return row
    sibling = proposal_path.parent / "proposal.patch"
    if sibling.exists() and sibling.is_file():
        return sibling
    fail("MISSING_STATE_INPUT")
    return sibling


def _apply_patch(*, root: Path, patch_path: Path, reverse: bool) -> bool:
    cmd = ["git", "apply"]
    if reverse:
        cmd.append("-R")
    cmd.append(str(patch_path))
    run = subprocess.run(
        cmd,
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return int(run.returncode) == 0


def _select_best(rows: list[tuple[Path, dict[str, Any]]]) -> tuple[Path, dict[str, Any]] | None:
    eligible: list[tuple[Path, dict[str, Any]]] = []
    for row in rows:
        _path, payload = row
        if str(payload.get("risk_tag", "")).strip() not in {"LOW", "MED", "MEDIUM"}:
            continue
        if not bool(payload.get("fast_gates_pass_b", False)):
            continue
        if not _proposal_tests_pass(payload):
            continue
        touched = _touched_paths_from_proposal(payload)
        if not touched:
            continue
        eligible.append(row)
    if not eligible:
        return None
    eligible.sort(key=_proposal_sort_key)
    return eligible[0]


def run(*, campaign_pack: Path, out_dir: Path) -> None:
    pack = _load_pack(campaign_pack)
    root = repo_root()
    proposals_glob = str(pack.get("proposals_glob", "runs/*/shadow/proposals/*/proposal_v1.json"))
    rows = _proposal_rows(root, proposals_glob)
    winner = _select_best(rows)

    state_root = out_dir.resolve() / "daemon" / "rsi_omega_apply_shadow_proposal_v1" / "state"
    reports_dir = state_root / "reports"
    promotion_dir = state_root / "promotion"
    for path in [reports_dir, promotion_dir]:
        path.mkdir(parents=True, exist_ok=True)

    if winner is None:
        report_payload = {
            "schema_version": "shadow_apply_report_v1",
            "report_id": "sha256:" + ("0" * 64),
            "selected": None,
            "reason": "NO_ELIGIBLE_PROPOSAL",
        }
        no_id = dict(report_payload)
        no_id.pop("report_id", None)
        report_payload["report_id"] = canon_hash_obj(no_id)
        write_canon_json(reports_dir / "shadow_apply_report_v1.json", report_payload)
        print("OK")
        return

    proposal_path, proposal_payload = winner
    touched_paths = _touched_paths_from_proposal(proposal_payload)
    if not touched_paths:
        fail("FORBIDDEN_PATH")
    patch_path = _resolve_patch_path(root=root, payload=proposal_payload, proposal_path=proposal_path)

    from tools.omega.omega_test_router_v1 import route_and_run

    triage_report = route_and_run(touched_paths=touched_paths, mode="triage", repo_root=root)
    write_canon_json(reports_dir / "omega_test_router_triage_report_v1.json", triage_report)
    if str(triage_report.get("result", "")) != "PASS":
        report_payload = {
            "schema_version": "shadow_apply_report_v1",
            "report_id": "sha256:" + ("0" * 64),
            "selected": {
                "proposal_path": str(proposal_path.relative_to(root)),
                "proposal_id": str(proposal_payload.get("proposal_id", "")),
                "expected_stps_delta_q32": max(0, int(proposal_payload.get("expected_stps_delta_q32", 0))),
                "risk_tag": str(proposal_payload.get("risk_tag", "")),
                "touched_paths": touched_paths,
                "patch_path": str(patch_path.relative_to(root)),
            },
            "reason": "TRIAGE_TESTS_FAILED",
            "triage_report_id": str(triage_report.get("report_id", "")),
        }
        no_id = dict(report_payload)
        no_id.pop("report_id", None)
        report_payload["report_id"] = canon_hash_obj(no_id)
        write_canon_json(reports_dir / "shadow_apply_report_v1.json", report_payload)
        print("OK")
        return

    before_metrics = _benchmark_eval(
        root=root,
        runs_root=state_root / "coreopt_eval_runs_before",
        series_prefix="coreopt_eval_before",
    )
    if not bool((before_metrics.get("bench") or {}).get("pass_b", False)):
        report_payload = {
            "schema_version": "shadow_apply_report_v1",
            "report_id": "sha256:" + ("0" * 64),
            "selected": {
                "proposal_path": str(proposal_path.relative_to(root)),
                "proposal_id": str(proposal_payload.get("proposal_id", "")),
                "expected_stps_delta_q32": max(0, int(proposal_payload.get("expected_stps_delta_q32", 0))),
                "risk_tag": str(proposal_payload.get("risk_tag", "")),
                "touched_paths": touched_paths,
                "patch_path": str(patch_path.relative_to(root)),
            },
            "reason": "BASELINE_BENCH_FAILED",
            "before_metrics": before_metrics,
        }
        no_id = dict(report_payload)
        no_id.pop("report_id", None)
        report_payload["report_id"] = canon_hash_obj(no_id)
        write_canon_json(reports_dir / "shadow_apply_report_v1.json", report_payload)
        print("OK")
        return

    apply_ok = _apply_patch(root=root, patch_path=patch_path, reverse=False)
    if not apply_ok:
        report_payload = {
            "schema_version": "shadow_apply_report_v1",
            "report_id": "sha256:" + ("0" * 64),
            "selected": {
                "proposal_path": str(proposal_path.relative_to(root)),
                "proposal_id": str(proposal_payload.get("proposal_id", "")),
                "expected_stps_delta_q32": max(0, int(proposal_payload.get("expected_stps_delta_q32", 0))),
                "risk_tag": str(proposal_payload.get("risk_tag", "")),
                "touched_paths": touched_paths,
                "patch_path": str(patch_path.relative_to(root)),
            },
            "reason": "PATCH_APPLY_FAILED",
        }
        no_id = dict(report_payload)
        no_id.pop("report_id", None)
        report_payload["report_id"] = canon_hash_obj(no_id)
        write_canon_json(reports_dir / "shadow_apply_report_v1.json", report_payload)
        print("OK")
        return

    suite = _run_full_self_opt_suite(
        root=root,
        before_metrics=before_metrics,
        runs_root=state_root / "coreopt_eval_runs",
    )
    accepted = bool(suite.get("suite_pass_b", False))
    proposal_payload_updated = dict(proposal_payload)
    proposal_payload_updated["accepted_b"] = bool(accepted)
    proposal_path.write_text(
        json.dumps(proposal_payload_updated, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    if not accepted:
        _apply_patch(root=root, patch_path=patch_path, reverse=True)

    report_payload = {
        "schema_version": "shadow_apply_report_v1",
        "report_id": "sha256:" + ("0" * 64),
        "selected": {
            "proposal_path": str(proposal_path.relative_to(root)),
            "proposal_id": str(proposal_payload.get("proposal_id", "")),
            "expected_stps_delta_q32": max(0, int(proposal_payload.get("expected_stps_delta_q32", 0))),
            "risk_tag": str(proposal_payload.get("risk_tag", "")),
            "touched_paths": touched_paths,
            "patch_path": str(patch_path.relative_to(root)),
        },
        "accepted_b": bool(accepted),
        "suite": suite,
    }
    if not accepted:
        report_payload["reason"] = "SELF_OPT_SUBVERIFIER_FAILED"
    no_id = dict(report_payload)
    no_id.pop("report_id", None)
    report_payload["report_id"] = canon_hash_obj(no_id)
    write_canon_json(reports_dir / "shadow_apply_report_v1.json", report_payload)

    if not accepted:
        print("OK")
        return

    bundle_payload = {
        "schema_version": "omega_shadow_apply_promotion_bundle_v1",
        "bundle_id": "sha256:" + ("0" * 64),
        "campaign_id": "rsi_omega_apply_shadow_proposal_v1",
        "proposal_id": str(proposal_payload.get("proposal_id", "")),
        "touched_paths": touched_paths,
        "proposal_artifact_rel": str(proposal_path.relative_to(root)),
        "report_rel": "daemon/rsi_omega_apply_shadow_proposal_v1/state/reports/shadow_apply_report_v1.json",
    }
    _, bundle_obj, _ = write_hashed_json(
        promotion_dir,
        "omega_shadow_apply_promotion_bundle_v1.json",
        bundle_payload,
        id_field="bundle_id",
    )
    emit_test_plan_receipt(
        promotion_dir=promotion_dir,
        touched_paths=[str(row) for row in bundle_obj.get("touched_paths", []) if isinstance(row, str)],
        mode="promotion",
    )
    print("OK")


def main() -> None:
    parser = argparse.ArgumentParser(prog="campaign_apply_shadow_proposal_v1")
    parser.add_argument("--campaign_pack", required=True)
    parser.add_argument("--out_dir", required=True)
    args = parser.parse_args()
    run(campaign_pack=Path(args.campaign_pack), out_dir=Path(args.out_dir))


if __name__ == "__main__":
    main()
