"""Self-optimization campaign for Omega core modules (v1)."""

from __future__ import annotations

import argparse
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
    "CDEL-v2/cdel/v18_0/verify_rsi_",
)
_DEFAULT_MICROBENCH_TICKS_U64 = 20


def _load_pack(path: Path) -> dict[str, Any]:
    payload = load_canon_dict(path)
    if str(payload.get("schema_version", "")).strip() != "rsi_omega_self_optimize_core_pack_v1":
        fail("SCHEMA_FAIL")
    ticks_u64 = int(payload.get("microbench_ticks_u64", _DEFAULT_MICROBENCH_TICKS_U64))
    if ticks_u64 <= 0:
        fail("SCHEMA_FAIL")
    return payload


def _latest_hotspot_stage_id(root: Path) -> str:
    rows = sorted(root.glob("runs/**/sha256_*.omega_hotspots_v1.json"), key=lambda path: path.as_posix())
    for path in reversed(rows):
        payload = load_canon_dict(path)
        if payload.get("schema_version") != "omega_hotspots_v1":
            continue
        top = payload.get("top_hotspots")
        if not isinstance(top, list) or not top:
            continue
        first = top[0]
        if isinstance(first, dict):
            stage_id = str(first.get("stage_id", "")).strip()
            if stage_id:
                return stage_id
    return "core"


def _target_path_for_stage(stage_id: str) -> str:
    mapping = {
        "dispatch": "CDEL-v2/cdel/v18_0/omega_executor_v1.py",
        "subverify": "CDEL-v2/cdel/v18_0/omega_verifier_worker_v1.py",
        "promote": "CDEL-v2/cdel/v18_0/omega_promoter_v1.py",
        "activate": "orchestrator/omega_v18_0/applier_v1.py",
        "observe": "orchestrator/omega_v18_0/observer_v1.py",
        "diagnose": "orchestrator/omega_v18_0/diagnoser_v1.py",
        "decide": "orchestrator/omega_v18_0/decider_v1.py",
        "verifier": "CDEL-v2/cdel/v18_0/omega_verifier_worker_v1.py",
        "tree_hash": "CDEL-v2/cdel/v18_0/omega_common_v1.py",
        "schema_validate": "CDEL-v2/cdel/v18_0/omega_common_v1.py",
    }
    return mapping.get(str(stage_id), "orchestrator/omega_v18_0/coordinator_v1.py")


def _validate_touched_paths(paths: list[str]) -> None:
    for value in paths:
        path_rel = require_relpath(value)
        if any(path_rel.startswith(prefix) for prefix in _FORBIDDEN_PATCH_PREFIXES):
            fail("FORBIDDEN_PATH")
        if not any(path_rel.startswith(prefix) for prefix in _ALLOWED_PATCH_PREFIXES):
            fail("FORBIDDEN_PATH")


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
        "pass": int(run.returncode) == 0,
        "stdout_tail": "\n".join(run.stdout.splitlines()[-20:]),
        "stderr_tail": "\n".join(run.stderr.splitlines()[-20:]),
    }


def _apply_deterministic_hotspot_patch(*, root: Path, target_path: str, stage_id: str) -> tuple[bool, str]:
    target_abs = (root / target_path).resolve()
    if not target_abs.exists() or not target_abs.is_file():
        fail("MISSING_STATE_INPUT")
    marker = f"# core-opt target hint: {stage_id}"
    text = target_abs.read_text(encoding="utf-8")
    if marker in text:
        return False, marker
    if text and not text.endswith("\n"):
        text += "\n"
    text += marker + "\n"
    target_abs.write_text(text, encoding="utf-8")
    return True, marker


def _stage_median_ns(timings_payload: dict[str, Any], stage_id: str) -> int:
    buckets = timings_payload.get("action_buckets")
    if not isinstance(buckets, dict):
        return 0
    run_bucket = buckets.get("RUN_*")
    if not isinstance(run_bucket, dict):
        return 0
    stage_ns = run_bucket.get("stage_ns")
    if not isinstance(stage_ns, dict):
        return 0
    stage_row = stage_ns.get(stage_id)
    if not isinstance(stage_row, dict):
        return 0
    return max(0, int(float(stage_row.get("median_ns", 0.0))))


def _run_microbench(*, root: Path, runs_root: Path, series_prefix: str, ticks_u64: int) -> dict[str, Any]:
    run_dir = runs_root / series_prefix
    shutil.rmtree(run_dir, ignore_errors=True)
    cmd = [
        sys.executable,
        str(root / "tools" / "omega" / "omega_benchmark_suite_v1.py"),
        "--ticks",
        str(max(1, int(ticks_u64))),
        "--series_prefix",
        series_prefix,
        "--runs_root",
        str(runs_root),
    ]
    run = _run_cmd(cmd, cwd=root)
    scorecard_path = run_dir / "OMEGA_RUN_SCORECARD_v1.json"
    timings_path = run_dir / "OMEGA_TIMINGS_AGG_v1.json"
    scorecard = load_canon_dict(scorecard_path) if scorecard_path.exists() else {}
    timings = load_canon_dict(timings_path) if timings_path.exists() else {}
    return {
        "run_ok": bool(run["pass"]),
        "run_dir": run_dir.as_posix(),
        "stps_non_noop_q32": max(0, int(scorecard.get("median_stps_non_noop_q32", 0))),
        "dispatch_ns_median_u64": _stage_median_ns(timings, "dispatch_campaign"),
        "subverify_ns_median_u64": _stage_median_ns(timings, "run_subverifier"),
    }


def run(*, campaign_pack: Path, out_dir: Path) -> None:
    pack = _load_pack(campaign_pack)
    root = repo_root()
    stage_id = _latest_hotspot_stage_id(root)
    target_path = _target_path_for_stage(stage_id)
    touched_paths = [target_path]
    _validate_touched_paths(touched_paths)

    ticks_u64 = int(pack.get("microbench_ticks_u64", _DEFAULT_MICROBENCH_TICKS_U64))

    state_root = out_dir.resolve() / "daemon" / "rsi_omega_self_optimize_core_v1" / "state"
    reports_dir = state_root / "reports"
    promotion_dir = state_root / "promotion"
    artifacts_dir = state_root / "artifacts"
    for path in [reports_dir, promotion_dir, artifacts_dir]:
        path.mkdir(parents=True, exist_ok=True)

    from tools.omega.omega_test_router_v1 import route_and_run

    triage_report = route_and_run(touched_paths=touched_paths, mode="triage", repo_root=root)
    write_canon_json(reports_dir / "omega_test_router_triage_report_v1.json", triage_report)
    triage_pass_b = str(triage_report.get("result", "")) == "PASS"

    tests: list[dict[str, Any]] = []
    tests.append(
        {
            "cmd": ["omega_test_router_v1", "--mode", "triage"],
            "return_code": 0 if triage_pass_b else 1,
            "pass": bool(triage_pass_b),
            "stdout_tail": str(triage_report.get("report_id", "")),
            "stderr_tail": "",
        }
    )
    if not triage_pass_b:
        report_payload: dict[str, Any] = {
            "schema_version": "core_opt_report_v1",
            "report_id": "sha256:" + ("0" * 64),
            "hotspot_stage_id": stage_id,
            "target_path": target_path,
            "before_after": {
                "stps_non_noop_q32": {"before_q32": 0, "after_q32": 0},
                "dispatch_ns_median_u64": {"before_u64": 0, "after_u64": 0},
                "subverify_ns_median_u64": {"before_u64": 0, "after_u64": 0},
            },
            "microbench_runs": {"before": {}, "after": {}},
            "tests_executed": tests,
            "touched_paths": touched_paths,
            "worktree_patch_applied_b": False,
            "worktree_patch_marker": "triage_failed",
        }
        report_no_id = dict(report_payload)
        report_no_id.pop("report_id", None)
        report_payload["report_id"] = canon_hash_obj(report_no_id)
        write_canon_json(reports_dir / "core_opt_report_v1.json", report_payload)
        print("OK")
        return

    tests.append(
        _run_cmd(
            [
                sys.executable,
                "-m",
                "py_compile",
                "orchestrator/omega_v18_0/coordinator_v1.py",
                "CDEL-v2/cdel/v18_0/omega_run_scorecard_v1.py",
                "tools/omega/omega_benchmark_suite_v1.py",
            ],
            cwd=root,
        )
    )
    patch_applied_b, patch_marker = _apply_deterministic_hotspot_patch(
        root=root,
        target_path=target_path,
        stage_id=stage_id,
    )
    tests.append(
        _run_cmd(
            [sys.executable, "-m", "py_compile", target_path],
            cwd=root,
        )
    )

    micro_runs_root = state_root / "microbench_runs"
    before = _run_microbench(
        root=root,
        runs_root=micro_runs_root,
        series_prefix="coreopt_before",
        ticks_u64=ticks_u64,
    )
    after = _run_microbench(
        root=root,
        runs_root=micro_runs_root,
        series_prefix="coreopt_after",
        ticks_u64=ticks_u64,
    )

    patch_rel = "tools/omega/CORE_OPT_PLACEHOLDER_v1.patch"
    patch_path = artifacts_dir / "CORE_OPT_PLACEHOLDER_v1.patch"
    git_diff = subprocess.run(
        ["git", "diff", "--", target_path],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    patch_text = git_diff.stdout
    if not patch_text:
        patch_text = "\n".join(
            [
                f"# hotspot_stage_id={stage_id}",
                f"# target_path={target_path}",
                "# deterministic core-opt patch produced no content diff",
                "",
            ]
        )
    patch_path.write_text(patch_text, encoding="utf-8")

    report_payload: dict[str, Any] = {
        "schema_version": "core_opt_report_v1",
        "report_id": "sha256:" + ("0" * 64),
        "hotspot_stage_id": stage_id,
        "target_path": target_path,
        "before_after": {
            "stps_non_noop_q32": {
                "before_q32": int(before["stps_non_noop_q32"]),
                "after_q32": int(after["stps_non_noop_q32"]),
            },
            "dispatch_ns_median_u64": {
                "before_u64": int(before["dispatch_ns_median_u64"]),
                "after_u64": int(after["dispatch_ns_median_u64"]),
            },
            "subverify_ns_median_u64": {
                "before_u64": int(before["subverify_ns_median_u64"]),
                "after_u64": int(after["subverify_ns_median_u64"]),
            },
        },
        "microbench_runs": {
            "before": before,
            "after": after,
        },
        "tests_executed": tests,
        "touched_paths": touched_paths,
        "worktree_patch_applied_b": bool(patch_applied_b),
        "worktree_patch_marker": patch_marker,
    }
    report_no_id = dict(report_payload)
    report_no_id.pop("report_id", None)
    report_payload["report_id"] = canon_hash_obj(report_no_id)
    report_path = reports_dir / "core_opt_report_v1.json"
    write_canon_json(report_path, report_payload)

    bundle_payload = {
        "schema_version": "omega_core_opt_promotion_bundle_v1",
        "bundle_id": "sha256:" + ("0" * 64),
        "campaign_id": "rsi_omega_self_optimize_core_v1",
        "hotspot_stage_id": stage_id,
        "touched_paths": touched_paths,
        "patch_paths": [patch_rel],
        "core_opt_report_rel": "daemon/rsi_omega_self_optimize_core_v1/state/reports/core_opt_report_v1.json",
    }
    _, bundle_obj, _ = write_hashed_json(
        promotion_dir,
        "omega_core_opt_promotion_bundle_v1.json",
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
    parser = argparse.ArgumentParser(prog="campaign_self_optimize_core_v1")
    parser.add_argument("--campaign_pack", required=True)
    parser.add_argument("--out_dir", required=True)
    args = parser.parse_args()
    run(campaign_pack=Path(args.campaign_pack), out_dir=Path(args.out_dir))


if __name__ == "__main__":
    main()
