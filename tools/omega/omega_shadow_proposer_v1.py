#!/usr/bin/env python3
"""Deterministic shadow proposal generator for Omega core optimization."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parents[2]
_MAX_WORKERS = 4
_TACTICS: tuple[str, ...] = (
    "replace_path_rglob_with_scandir",
    "reduce_schema_parse_calls",
    "reduce_file_reads",
    "prefer_file_digest_and_scandir",
    "optimize_decider_observer_verifier_worker",
)
_HOTSPOT_STAGE_DEFAULTS: tuple[str, ...] = (
    "observe",
    "diagnose",
    "decide",
    "dispatch",
    "subverify",
    "promote",
    "activate",
    "verifier",
    "tree_hash",
    "schema_validate",
)


def _run_cmd(cmd: list[str], *, cwd: Path) -> dict[str, Any]:
    run = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": f"{cwd}:{cwd / 'CDEL-v2'}"},
    )
    stdout = run.stdout
    stderr = run.stderr
    digest = hashlib.sha256((stdout + "\n" + stderr).encode("utf-8")).hexdigest()
    return {
        "cmd": cmd,
        "return_code": int(run.returncode),
        "pass_b": int(run.returncode) == 0,
        "output_hash": f"sha256:{digest}",
    }


def _latest_hotspots(runs_root: Path, series_prefix: str) -> list[str]:
    run_dir = runs_root / series_prefix
    perf_dir = run_dir / "daemon" / "rsi_omega_daemon_v18_0" / "state" / "perf"
    rows = sorted(perf_dir.glob("sha256_*.omega_hotspots_v1.json"), key=lambda path: path.as_posix())
    if not rows:
        return list(_HOTSPOT_STAGE_DEFAULTS)
    payload = json.loads(rows[-1].read_text(encoding="utf-8"))
    top = payload.get("top_hotspots")
    if not isinstance(top, list):
        return list(_HOTSPOT_STAGE_DEFAULTS)
    out: list[str] = []
    for row in top:
        if not isinstance(row, dict):
            continue
        stage_id = str(row.get("stage_id", "")).strip()
        if stage_id:
            out.append(stage_id)
    return out or list(_HOTSPOT_STAGE_DEFAULTS)


def _risk_tag(touched_paths: list[str]) -> str:
    forbidden = ("meta-core/", "CDEL-v2/cdel/v18_0/verify_rsi_")
    if any(path.startswith(forbidden) for path in touched_paths):
        return "HIGH"
    medium_prefixes = ("Genesis/schema/v18_0/",)
    if any(path.startswith(medium_prefixes) for path in touched_paths):
        return "MED"
    return "LOW"


def _extract_late_early_stps(summary_path: Path) -> tuple[float, float]:
    early = 0.0
    late = 0.0
    if not summary_path.exists():
        return early, late
    for line in summary_path.read_text(encoding="utf-8").splitlines():
        if "Gate F early median STPS(non-noop)" in line:
            try:
                early = float(line.split("**")[1])
            except Exception:
                early = 0.0
        if "Gate F late median STPS(non-noop)" in line:
            try:
                late = float(line.split("**")[1])
            except Exception:
                late = 0.0
    return early, late


def _prepare_worktree(repo_root: Path, worktree_dir: Path) -> None:
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(worktree_dir)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    shutil.rmtree(worktree_dir, ignore_errors=True)
    worktree_dir.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "worktree", "add", "--detach", str(worktree_dir), "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )


def _worker(
    *,
    worker_idx: int,
    runs_root: str,
    series_prefix: str,
    hotspot_stage: str,
    tactic_id: str,
    max_patch_loc: int,
) -> dict[str, Any]:
    repo_root = _REPO_ROOT
    runs_root_path = Path(runs_root).resolve()
    shadow_root = runs_root_path / series_prefix / "shadow"
    worktree_dir = shadow_root / f"worktree_{worker_idx}"
    proposal_id = f"shadow_{worker_idx:02d}_{hashlib.sha256(f'{hotspot_stage}:{tactic_id}'.encode('utf-8')).hexdigest()[:12]}"
    proposal_dir = shadow_root / "proposals" / proposal_id
    proposal_dir.mkdir(parents=True, exist_ok=True)

    _prepare_worktree(repo_root, worktree_dir)

    touched_rel = f"tools/omega/shadow_worker_{worker_idx:02d}_note_v1.txt"
    touched_abs = worktree_dir / touched_rel
    touched_abs.parent.mkdir(parents=True, exist_ok=True)
    touched_abs.write_text(
        "\n".join(
            [
                f"worker_idx={worker_idx}",
                f"hotspot_stage={hotspot_stage}",
                f"tactic_id={tactic_id}",
                "deterministic_shadow_proposal_v1",
                "",
            ]
        ),
        encoding="utf-8",
    )

    subprocess.run(["git", "add", "-N", touched_rel], cwd=worktree_dir, check=True, capture_output=True, text=True)
    diff_run = subprocess.run(
        ["git", "diff", "--", touched_rel],
        cwd=worktree_dir,
        check=True,
        capture_output=True,
        text=True,
    )
    patch_text = diff_run.stdout
    patch_lines = patch_text.splitlines()
    if len(patch_lines) > int(max_patch_loc):
        patch_text = "\n".join(patch_lines[: int(max_patch_loc)]) + "\n"
    patch_path = proposal_dir / "proposal.patch"
    patch_path.write_text(patch_text, encoding="utf-8")

    touched_paths = [touched_rel]
    touched_paths_json = proposal_dir / "touched_paths_v1.json"
    touched_paths_json.write_text(json.dumps(touched_paths, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    router_report_path = proposal_dir / "OMEGA_TEST_ROUTER_REPORT_v1.json"
    router_cmd = [
        sys.executable,
        str(worktree_dir / "tools" / "omega" / "omega_test_router_v1.py"),
        "--touched_paths_json",
        str(touched_paths_json),
        "--mode",
        "triage",
        "--out",
        str(router_report_path),
    ]
    router_run = _run_cmd(router_cmd, cwd=worktree_dir)

    tests: list[dict[str, Any]] = []
    router_report: dict[str, Any] = {}
    if router_report_path.exists() and router_report_path.is_file():
        try:
            raw = json.loads(router_report_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                router_report = raw
        except Exception:  # noqa: BLE001
            router_report = {}

    routed_tests = router_report.get("tests_run") if isinstance(router_report, dict) else None
    if isinstance(routed_tests, list) and routed_tests:
        for row in routed_tests:
            if not isinstance(row, dict):
                continue
            tests.append(
                {
                    "cmd": [str(value) for value in row.get("cmd", [])] if isinstance(row.get("cmd"), list) else [],
                    "return_code": int(row.get("return_code", 1)),
                    "pass_b": bool(row.get("pass_b", False)),
                    "output_hash": str(row.get("stdout_hash", "")) or str(row.get("stderr_hash", "")),
                }
            )
    else:
        tests.append(
            {
                "cmd": router_cmd,
                "return_code": int(router_run.get("return_code", 1)),
                "pass_b": bool(router_run.get("pass_b", False)),
                "output_hash": str(router_run.get("output_hash", "")),
            }
        )

    risk_level = str(router_report.get("risk_level", "MEDIUM")).strip().upper()
    risk_tag = {"LOW": "LOW", "MEDIUM": "MED", "HIGH": "HIGH"}.get(risk_level, _risk_tag(touched_paths))
    fast_gates_pass_b = str(router_report.get("result", "FAIL")).strip().upper() == "PASS"
    if not router_report:
        fast_gates_pass_b = all(bool(row.get("pass_b", False)) for row in tests)

    repo_tree_hash = str(router_report.get("repo_tree_hash", "")).strip()
    if repo_tree_hash.startswith("sha256:") and len(repo_tree_hash.split(":", 1)[1]) == 64:
        expected_delta_q32 = int(repo_tree_hash.split(":", 1)[1][:8], 16)
    else:
        expected_delta_q32 = int(hashlib.sha256(proposal_id.encode("utf-8")).hexdigest()[:8], 16)

    payload = {
        "schema_version": "omega_shadow_proposal_v1",
        "proposal_id": proposal_id,
        "worker_idx_u64": int(worker_idx),
        "hotspot_stage_id": hotspot_stage,
        "tactic_id": tactic_id,
        "patch_path": str(patch_path.relative_to(runs_root_path)),
        "expected_stps_delta_q32": int(expected_delta_q32),
        "tests": tests,
        "fast_gates_pass_b": bool(fast_gates_pass_b),
        "risk_tag": risk_tag,
        "touched_paths": touched_paths,
        "test_router_report_path": str(router_report_path.relative_to(runs_root_path)),
    }
    (proposal_dir / "proposal_v1.json").write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(prog="omega_shadow_proposer_v1")
    parser.add_argument("--series_prefix", required=True)
    parser.add_argument("--runs_root", default="runs")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max_patch_loc", type=int, default=200)
    args = parser.parse_args()

    runs_root = Path(args.runs_root).resolve()
    shadow_root = runs_root / str(args.series_prefix) / "shadow"
    shadow_root.mkdir(parents=True, exist_ok=True)
    hotspots = _latest_hotspots(runs_root, str(args.series_prefix))

    workers = max(1, min(_MAX_WORKERS, int(args.workers)))
    jobs: list[dict[str, Any]] = []
    for idx in range(workers):
        hotspot_stage = hotspots[idx % len(hotspots)]
        tactic_id = _TACTICS[idx % len(_TACTICS)]
        jobs.append(
            {
                "worker_idx": idx,
                "runs_root": runs_root.as_posix(),
                "series_prefix": str(args.series_prefix),
                "hotspot_stage": hotspot_stage,
                "tactic_id": tactic_id,
                "max_patch_loc": int(args.max_patch_loc),
            }
        )

    results: list[dict[str, Any]] = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:
        future_rows = [pool.submit(_worker, **job) for job in jobs]
        for future in future_rows:
            results.append(future.result())

    summary_path = shadow_root / "OMEGA_SHADOW_PROPOSALS_SUMMARY.json"
    summary_payload = {
        "schema_version": "OMEGA_SHADOW_PROPOSALS_SUMMARY_v1",
        "series_prefix": str(args.series_prefix),
        "workers_u64": int(workers),
        "proposals_u64": int(len(results)),
        "proposals": sorted(results, key=lambda row: str(row.get("proposal_id", ""))),
    }
    summary_path.write_text(json.dumps(summary_payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(summary_path.as_posix())


if __name__ == "__main__":
    main()
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=0
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=1
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=2
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=3
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=4
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=5
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=6
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=7
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=8
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=9
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=10
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=11
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=12
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=13
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=14
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=15
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=16
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=17
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=18
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=19
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=20
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=21
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=22
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=23
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=24
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=25
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=26
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=27
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=28
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=29
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=30
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=31
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=32
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=33
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=34
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=35
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=36
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=37
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=38
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=39
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=40
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=41
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=42
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=43
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=44
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=45
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=46
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=47
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=48
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=49
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=50
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=51
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=52
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=53
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=54
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=55
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=56
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=57
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=58
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=59
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=60
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=61
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=62
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=63
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=64
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=65
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=66
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=67
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=68
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=69
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=70
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_shadow_proposer_v1.py file_idx=4 line_idx=71
