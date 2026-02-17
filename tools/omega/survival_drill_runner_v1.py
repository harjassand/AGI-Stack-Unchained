#!/usr/bin/env python3
"""Survival Drill v1 runner (sandbox-only).

Runs omega ticks with:
- CCAP anti-bypass tests enforced
- no-human-commit guard (OMEGA_SURVIVAL_DRILL=1) enforced by coordinator
- hard tick budget (default 100)
and captures per-tick evidence under runs/<series>/survival_drill/.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from tools.omega.make_meta_core_sandbox_v1 import create_meta_core_sandbox


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _sha256_prefixed(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _git(args: list[str]) -> str:
    run = subprocess.run(["git", *args], cwd=_REPO_ROOT, check=True, capture_output=True, text=True)
    return run.stdout


def _latest_dispatch_dir(state_root: Path) -> Path | None:
    dispatch_root = state_root / "dispatch"
    if not dispatch_root.exists():
        return None
    candidates = [p for p in dispatch_root.iterdir() if p.is_dir()]
    if not candidates:
        return None
    candidates.sort(key=lambda p: (p.stat().st_mtime_ns, p.as_posix()))
    return candidates[-1]


def _latest_observation(state_root: Path) -> dict[str, Any] | None:
    obs_dir = state_root / "observations"
    if not obs_dir.exists():
        return None
    # Observation filenames are content-addressed; lexicographic order is not correlated with tick.
    # Select by max tick_u64 for stable per-tick evidence.
    paths = list(obs_dir.glob("sha256_*.omega_observation_report_v1.json"))
    if not paths:
        return None
    best: tuple[int, str, dict[str, Any]] | None = None
    for p in paths:
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        tick = payload.get("tick_u64")
        try:
            tick_u64 = int(tick)
        except Exception:
            continue
        key = (tick_u64, p.as_posix(), payload)
        if best is None or (key[0] > best[0]) or (key[0] == best[0] and key[1] > best[1]):
            best = key
    return best[2] if best is not None else None


def _run_py(cmd: list[str], *, env: dict[str, str] | None = None) -> None:
    run = subprocess.run(cmd, cwd=_REPO_ROOT, env=env, text=True, capture_output=True, check=False)
    if int(run.returncode) != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\nstdout:\n{run.stdout}\nstderr:\n{run.stderr}")


def _run_pytest_survival_anti_bypass() -> None:
    _run_py(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "CDEL-v2/cdel/v18_0/tests_omega_daemon/test_survival_drill_ccap_anti_bypass_v1.py",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(prog="survival_drill_runner_v1")
    parser.add_argument("--runs_root", default="runs")
    parser.add_argument("--series_prefix", default="")
    parser.add_argument(
        "--campaign_pack",
        default="campaigns/rsi_omega_daemon_survival_drill_v1/rsi_omega_daemon_pack_v1.json",
    )
    parser.add_argument("--tick_budget", type=int, default=100)
    parser.add_argument("--meta_core_mode", choices=("sandbox", "production"), default="sandbox")
    parser.add_argument("--allowed_authors", default="omega-bot,SH1_OPTIMIZER")
    args = parser.parse_args()

    runs_root = Path(args.runs_root).resolve()
    runs_root.mkdir(parents=True, exist_ok=True)
    series_prefix = str(args.series_prefix).strip()
    if not series_prefix:
        series_prefix = f"survival_drill_ccap_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
    run_dir = runs_root / series_prefix
    run_dir.mkdir(parents=True, exist_ok=True)

    # Ensure commits created by the runner are attributed to the agent identity.
    os.environ["GIT_AUTHOR_NAME"] = "omega-bot"
    os.environ["GIT_AUTHOR_EMAIL"] = "omega-bot@local"
    os.environ["GIT_COMMITTER_NAME"] = "omega-bot"
    os.environ["GIT_COMMITTER_EMAIL"] = "omega-bot@local"

    os.environ["OMEGA_SURVIVAL_DRILL"] = "1"
    os.environ["OMEGA_SURVIVAL_DRILL_ALLOWED_AUTHORS"] = str(args.allowed_authors)
    # Drill-only CCAP authorization expansion (prod pins remain unchanged).
    os.environ["OMEGA_AUTHORITY_PINS_REL"] = "authority/authority_pins_survival_drill_v1.json"
    os.environ["OMEGA_CCAP_PATCH_ALLOWLISTS_REL"] = "authority/ccap_patch_allowlists_survival_drill_v1.json"

    if str(args.meta_core_mode) == "production":
        meta_core_root = (_REPO_ROOT / "meta-core").resolve()
    else:
        meta_core_root = create_meta_core_sandbox(runs_root=runs_root, series=series_prefix).resolve()
    os.environ["OMEGA_META_CORE_ROOT"] = str(meta_core_root)
    os.environ["OMEGA_META_CORE_ACTIVATION_MODE"] = "live"
    os.environ["OMEGA_ALLOW_SIMULATE_ACTIVATION"] = "0"

    campaign_pack = (_REPO_ROOT / str(args.campaign_pack)).resolve()
    if not campaign_pack.exists():
        raise FileNotFoundError(f"missing campaign pack: {campaign_pack}")

    state_root = (run_dir / "daemon" / "rsi_omega_daemon_v18_0" / "state").resolve()
    drill_root = (run_dir / "survival_drill").resolve()
    drill_root.mkdir(parents=True, exist_ok=True)

    _write_json(
        drill_root / "SURVIVAL_DRILL_CONFIG_v1.json",
        {
            "schema_version": "SURVIVAL_DRILL_CONFIG_v1",
            "series_prefix": series_prefix,
            "tick_budget_u64": int(max(1, int(args.tick_budget))),
            "campaign_pack": str(campaign_pack),
            "meta_core_root": str(meta_core_root),
            "allowed_authors": str(args.allowed_authors),
            "started_at_utc": datetime.now(UTC).isoformat(),
        },
    )

    # Enforce anti-bypass tests before starting (fail-closed).
    _run_pytest_survival_anti_bypass()

    coordinator = __import__("orchestrator.omega_v18_0.coordinator_v1", fromlist=["run_tick"])
    run_tick = getattr(coordinator, "run_tick")

    prev_state_dir: Path | None = None
    start_head = _git(["rev-parse", "HEAD"]).strip()
    ge_promoted_b = False
    ge_campaign_id = "rsi_ge_symbiotic_optimizer_sh1_v0_1"
    for tick_u64 in range(1, int(max(1, int(args.tick_budget))) + 1):
        tick_dir = drill_root / f"tick_{tick_u64:04d}"
        tick_dir.mkdir(parents=True, exist_ok=True)

        _write_json(
            tick_dir / "git_pre_v1.json",
            {
                "head": _git(["rev-parse", "HEAD"]).strip(),
                "status": _git(["status", "--porcelain=v1", "-uno"]).splitlines(),
                "diff_name_only": _git(["diff", "--name-only"]).splitlines(),
            },
        )

        tick_started = time.monotonic()
        try:
            result = run_tick(
                campaign_pack=campaign_pack,
                out_dir=run_dir,
                tick_u64=int(tick_u64),
                prev_state_dir=prev_state_dir,
            )
            _write_json(tick_dir / "tick_result_v1.json", dict(result))
        except Exception as exc:  # noqa: BLE001
            _write_json(
                tick_dir / "tick_exception_v1.json",
                {"schema_version": "SURVIVAL_DRILL_TICK_EXCEPTION_v1", "tick_u64": tick_u64, "error": str(exc)},
            )
            return 2
        finally:
            _write_json(
                tick_dir / "timing_v1.json",
                {
                    "schema_version": "SURVIVAL_DRILL_TICK_TIMING_v1",
                    "tick_u64": tick_u64,
                    "elapsed_s": float(time.monotonic() - tick_started),
                },
            )

        prev_state_dir = state_root

        dispatch_dir = _latest_dispatch_dir(state_root)
        if dispatch_dir is not None:
            evidence: dict[str, Any] = {"dispatch_dir": dispatch_dir.as_posix()}
            # Record dispatch campaign + promotion outcome (we need to prove GE+CCAP actually ran).
            dispatch_receipts = sorted(dispatch_dir.glob("*.omega_dispatch_receipt_v1.json"), key=lambda p: p.as_posix())
            if dispatch_receipts:
                try:
                    d = json.loads(dispatch_receipts[-1].read_text(encoding="utf-8"))
                    evidence["dispatch_receipt"] = {"path": dispatch_receipts[-1].as_posix(), "campaign_id": d.get("campaign_id")}
                    if str(d.get("campaign_id", "")).strip() == ge_campaign_id:
                        promo_dir = dispatch_dir / "promotion"
                        promo_receipts = sorted(promo_dir.glob("*.omega_promotion_receipt_v1.json"), key=lambda p: p.as_posix())
                        promo_rows = []
                        for pr in promo_receipts:
                            try:
                                pd = json.loads(pr.read_text(encoding="utf-8"))
                            except Exception:
                                continue
                            res = pd.get("result") if isinstance(pd, dict) else None
                            status = res.get("status") if isinstance(res, dict) else None
                            reason = res.get("reason_code") if isinstance(res, dict) else None
                            promo_rows.append({"path": pr.as_posix(), "status": status, "reason_code": reason})
                            if str(status).strip() == "PROMOTED":
                                ge_promoted_b = True
                        evidence["ge_promotion_receipts"] = promo_rows
                        _write_json(
                            tick_dir / "ge_promotion_evidence_v1.json",
                            {
                                "schema_version": "SURVIVAL_DRILL_GE_PROMOTION_EVIDENCE_v1",
                                "tick_u64": tick_u64,
                                "dispatch_dir": dispatch_dir.as_posix(),
                                "ge_promoted_b": bool(ge_promoted_b),
                                "promotion_receipts": promo_rows,
                            },
                        )
                except Exception:
                    pass
            verifier_dir = dispatch_dir / "verifier"
            receipts = sorted(verifier_dir.glob("*.ccap_receipt_v1.json"), key=lambda p: p.as_posix())
            if (verifier_dir / "ccap_receipt_v1.json").exists():
                receipts.append(verifier_dir / "ccap_receipt_v1.json")
            evidence["ccap_receipts"] = [
                {"path": p.as_posix(), "sha256": _sha256_prefixed(p)} for p in receipts if p.exists() and p.is_file()
            ]
            _write_json(tick_dir / "ccap_receipt_evidence_v1.json", evidence)

        # Commit any activated patch changes (matches overnight runner semantics).
        try:
            from tools.omega.omega_overnight_runner_v1 import _stage_and_commit_livewire_tick  # type: ignore

            commit_row = _stage_and_commit_livewire_tick(repo_root=_REPO_ROOT, state_dir=state_root, tick_u64=tick_u64)
        except Exception as exc:  # noqa: BLE001
            _write_json(
                tick_dir / "commit_error_v1.json",
                {"schema_version": "SURVIVAL_DRILL_COMMIT_ERROR_v1", "tick_u64": tick_u64, "error": str(exc)},
            )
            commit_row = None

        if commit_row is not None:
            _write_json(tick_dir / "livewire_commit_v1.json", dict(commit_row))
            # Re-enforce anti-bypass tests after code changes land.
            _run_pytest_survival_anti_bypass()

        obs = _latest_observation(state_root)
        if isinstance(obs, dict):
            metrics = obs.get("metrics")
            cap_frontier = int(metrics.get("cap_frontier_u64", 0)) if isinstance(metrics, dict) else 0
            _write_json(
                tick_dir / "frontier_v1.json",
                {
                    "schema_version": "SURVIVAL_DRILL_FRONTIER_SNAPSHOT_v1",
                    "tick_u64": tick_u64,
                    "cap_frontier_u64": cap_frontier,
                },
            )
            if cap_frontier > 1 and ge_promoted_b:
                _write_json(
                    drill_root / "SURVIVAL_DRILL_SUCCESS_v1.json",
                    {
                        "schema_version": "SURVIVAL_DRILL_SUCCESS_v1",
                        "tick_u64": tick_u64,
                        "cap_frontier_u64": cap_frontier,
                        "ge_promoted_b": True,
                        "start_head": start_head,
                        "end_head": _git(["rev-parse", "HEAD"]).strip(),
                    },
                )
                return 0

    _write_json(
        drill_root / "SURVIVAL_DRILL_FAILURE_v1.json",
        {
            "schema_version": "SURVIVAL_DRILL_FAILURE_v1",
            "tick_budget_u64": int(args.tick_budget),
            "start_head": start_head,
            "end_head": _git(["rev-parse", "HEAD"]).strip(),
        },
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
