#!/usr/bin/env python3
"""Run the v19.0 Omega daemon loop and generate post-run evidence reports."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _pinned_pythonpath() -> str:
    ordered = [str(REPO_ROOT), str(REPO_ROOT / "CDEL-v2")]
    existing = str(os.environ.get("PYTHONPATH", "")).strip()
    if existing:
        return ":".join([*ordered, existing])
    return ":".join(ordered)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run v19 omega daemon loop + post-run coverage reports")
    parser.add_argument(
        "--campaign_pack",
        required=True,
        help="Path to a v19 omega daemon pack json (e.g. campaigns/rsi_omega_daemon_v19_0/rsi_omega_daemon_pack_v1.json)",
    )
    parser.add_argument("--ticks", type=int, required=True, help="Number of ticks to run")
    parser.add_argument("--out_root", default="runs/v19_full_loop", help="Output root directory (contains per-tick dirs)")
    parser.add_argument("--start_tick", type=int, default=1, help="Starting tick number")
    args = parser.parse_args()

    campaign_pack = Path(str(args.campaign_pack)).expanduser().resolve()
    out_root = Path(str(args.out_root)).expanduser().resolve()
    ticks = int(args.ticks)
    start_tick = int(args.start_tick)

    out_dir_pattern = (out_root / "tick_{tick:04d}").as_posix()

    out_root.mkdir(parents=True, exist_ok=True)
    if any(out_root.iterdir()):
        raise SystemExit(f"out_root must be empty for deterministic runs: {out_root}")

    env = dict(os.environ)
    env["PYTHONPATH"] = _pinned_pythonpath()
    # Default to safe activation behavior for local evidence runs.
    env.setdefault("OMEGA_META_CORE_ACTIVATION_MODE", "simulate")
    env.setdefault("OMEGA_ALLOW_SIMULATE_ACTIVATION", "1")
    # Polymath conquer/verify expects sealed dataset blobs in a store root.
    # Keep it deterministic + per-run by defaulting inside out_root.
    env.setdefault("OMEGA_POLYMATH_STORE_ROOT", str((out_root / "polymath_store").resolve()))

    seed_tool = (REPO_ROOT / "tools" / "polymath" / "polymath_seed_flagships_v1.py").resolve()
    seed_summary = out_root / "OMEGA_POLYMATH_SEED_FLAGSHIPS_SUMMARY_v1.json"
    subprocess.run(
        [
            sys.executable,
            str(seed_tool),
            "--store_root",
            str(env["OMEGA_POLYMATH_STORE_ROOT"]),
            "--summary_path",
            str(seed_summary),
        ],
        check=True,
        env=env,
    )

    subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator.rsi_omega_daemon_v19_0",
            "--mode",
            "loop",
            "--campaign_pack",
            str(campaign_pack),
            "--out_dir",
            out_dir_pattern,
            "--tick_u64",
            str(start_tick),
            "--ticks",
            str(ticks),
        ],
        check=True,
        env=env,
    )

    scan_tool = (REPO_ROOT / "tools" / "v19_hypothesis" / "scan_axis_bundle_coverage.py").resolve()
    scan_out = out_root / "V19_AXIS_BUNDLE_COVERAGE_SCAN_v1.json"
    subprocess.run(
        [
            sys.executable,
            str(scan_tool),
            "--root",
            str(out_root),
            "--out",
            str(scan_out),
        ],
        check=True,
        env=env,
    )

    attainment_tool = (REPO_ROOT / "tools" / "v19_runs" / "level_attainment_report_v1.py").resolve()
    subprocess.run(
        [
            sys.executable,
            str(attainment_tool),
            "--runs_root",
            str(out_root),
        ],
        check=True,
        env=env,
    )

    ladder_tool = (REPO_ROOT / "tools" / "v19_runs" / "v19_ladder_evidence_pipeline_v1.py").resolve()
    subprocess.run(
        [
            sys.executable,
            str(ladder_tool),
            "--runs_root",
            str(out_root),
        ],
        check=True,
        env=env,
    )

    gates_tool = (REPO_ROOT / "tools" / "v19_runs" / "omega_benchmark_gates_v19_v1.py").resolve()
    subprocess.run(
        [
            sys.executable,
            str(gates_tool),
            "--runs_root",
            str(out_root),
        ],
        check=True,
        env=env,
    )

    ge_evidence_tool = (REPO_ROOT / "tools" / "v19_runs" / "ge_dispatch_evidence_v1.py").resolve()
    subprocess.run(
        [
            sys.executable,
            str(ge_evidence_tool),
            "--runs_root",
            str(out_root),
        ],
        check=True,
        env=env,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
