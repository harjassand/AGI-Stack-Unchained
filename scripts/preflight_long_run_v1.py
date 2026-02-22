#!/usr/bin/env python3
"""Preflight runner for long disciplined mode (baseline/canary/frontier window)."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "CDEL-v2") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "CDEL-v2"))

from cdel.v1_7r.canon import canon_bytes
from cdel.v18_0.omega_common_v1 import canon_hash_obj, load_canon_dict


DEFAULT_PACK = "campaigns/rsi_omega_daemon_v19_0_long_run_v1/rsi_omega_daemon_pack_v1.json"
DEFAULT_RUN_ROOT = "runs/long_run_preflight_v1"
DEFAULT_SUMMARY = "LONG_RUN_PREFLIGHT_SUMMARY_v1.json"
DEFAULT_MAX_DISK_BYTES = 20 * 1024 * 1024 * 1024

TICK_INDEX_NAME = "long_run_tick_index_v1.jsonl"
PRUNE_INDEX_NAME = "long_run_prune_index_v1.jsonl"
HEAD_NAME = "long_run_head_v1.json"

MISSION_PAYLOAD_A = {
    "schema_name": "mission_request_v1",
    "schema_version": "v19_0",
    "enabled_b": True,
    "priority": "MED",
    "objective_tags": ["science"],
    "allowed_capability_ids": ["RSI_SAS_SCIENCE"],
    "notes": "preflight_mission_a",
}
MISSION_PAYLOAD_B = {
    "schema_name": "mission_request_v1",
    "schema_version": "v19_0",
    "enabled_b": True,
    "priority": "HIGH",
    "objective_tags": ["metasearch"],
    "allowed_capability_ids": ["RSI_SAS_METASEARCH"],
    "notes": "preflight_mission_b",
}

_OPAQUE_REASONS = {"unknown", "opaque", "unknown_reason", "opaque_reason"}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canon_bytes(payload) + b"\n")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected object at {path}")
    return payload


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if isinstance(row, dict):
            out.append(row)
    return out


def _latest_payload(dir_path: Path, suffix: str) -> tuple[dict[str, Any] | None, str | None]:
    if not dir_path.exists() or not dir_path.is_dir():
        return None, None
    rows = sorted(dir_path.glob(f"sha256_*.{suffix}"), key=lambda p: p.as_posix())
    if not rows:
        return None, None
    payload = load_canon_dict(rows[-1])
    digest = "sha256:" + rows[-1].name.split(".", 1)[0].split("_", 1)[1]
    return payload, digest


def _record_check(
    checks: list[dict[str, Any]],
    *,
    check_id: str,
    pass_b: bool,
    reason_code: str,
    detail: dict[str, Any] | None = None,
) -> None:
    checks.append(
        {
            "check_id": str(check_id),
            "pass_b": bool(pass_b),
            "reason_code": str(reason_code),
            "detail": detail or {},
        }
    )


def _run_harness(
    *,
    campaign_pack_rel: str,
    run_root_rel: str,
    start_tick_u64: int | None,
    max_ticks: int,
    max_disk_bytes: int,
    force_lane: str | None,
    force_eval: bool,
) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "run_long_disciplined_loop_v1.py"),
        "--campaign_pack",
        campaign_pack_rel,
        "--run_root",
        run_root_rel,
        "--max_ticks",
        str(int(max_ticks)),
        "--max_disk_bytes",
        str(int(max_disk_bytes)),
        "--stop_on_error",
    ]
    if start_tick_u64 is not None:
        cmd.extend(["--start_tick_u64", str(int(start_tick_u64))])
    if force_lane:
        cmd.extend(["--force_lane", str(force_lane).upper()])
    if force_eval:
        cmd.append("--force_eval")
    return subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def _verify_state(state_dir: Path) -> tuple[bool, str]:
    cmd = [
        sys.executable,
        "-m",
        "cdel.v19_0.verify_rsi_omega_daemon_v1",
        "--mode",
        "full",
        "--state_dir",
        str(state_dir),
    ]
    env = dict()
    env["PYTHONPATH"] = ".:CDEL-v2:Extension-1/agi-orchestrator"
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    ok = proc.returncode == 0 and "VALID" in (proc.stdout or "")
    return ok, out.strip()


def _health_gate_from_state(state_dir: Path, profile: dict[str, Any]) -> tuple[bool, dict[str, int]]:
    payload, _ = _latest_payload(state_dir / "long_run" / "health", "long_run_health_window_v1.json")
    rows = []
    if isinstance(payload, dict):
        rows_raw = payload.get("rows")
        if isinstance(rows_raw, list):
            rows = [row for row in rows_raw if isinstance(row, dict)]
    counts = {
        "invalid_count_u64": sum(1 for row in rows if bool(row.get("invalid_b", False))),
        "budget_exhaust_count_u64": sum(1 for row in rows if bool(row.get("budget_exhaust_b", False))),
        "route_disabled_count_u64": sum(1 for row in rows if bool(row.get("route_disabled_b", False))),
    }
    gate = profile.get("frontier_health_gate") if isinstance(profile.get("frontier_health_gate"), dict) else {}
    ok = (
        int(counts["invalid_count_u64"]) <= int(max(0, int(gate.get("max_invalid_u64", 0))))
        and int(counts["budget_exhaust_count_u64"]) <= int(max(0, int(gate.get("max_budget_exhaust_u64", 0))))
        and int(counts["route_disabled_count_u64"]) <= int(max(0, int(gate.get("max_route_disabled_u64", 0))))
    )
    return ok, counts


def _frontier_enabled_caps(profile: dict[str, Any], registry: dict[str, Any]) -> list[str]:
    lanes = profile.get("lanes")
    if not isinstance(lanes, dict):
        return []
    frontier_caps_raw = lanes.get("frontier_capability_ids")
    if not isinstance(frontier_caps_raw, list):
        return []
    frontier_caps = {str(row).strip() for row in frontier_caps_raw if str(row).strip()}

    registry_rows = registry.get("capabilities")
    if not isinstance(registry_rows, list):
        return []
    enabled: dict[str, bool] = {}
    for row in registry_rows:
        if not isinstance(row, dict):
            continue
        capability_id = str(row.get("capability_id", "")).strip()
        if not capability_id:
            continue
        enabled[capability_id] = bool(row.get("enabled", False))
    return sorted([cap for cap in frontier_caps if enabled.get(cap, False)])


def _is_opaque_reason(value: Any) -> bool:
    raw = str(value or "").strip().lower()
    return raw in _OPAQUE_REASONS


def _read_tick_rows(run_root: Path) -> list[dict[str, Any]]:
    rows = _load_jsonl(run_root / "index" / TICK_INDEX_NAME)
    rows = [row for row in rows if isinstance(row, dict)]
    rows.sort(key=lambda row: int(row.get("tick_u64", -1)))
    return rows


def _read_pruned_ticks(run_root: Path) -> set[int]:
    rows = _load_jsonl(run_root / "index" / PRUNE_INDEX_NAME)
    return {int(row.get("tick_u64", -1)) for row in rows if isinstance(row, dict)}


def _env_truthy(name: str, *, default: bool = False) -> bool:
    raw = str(os.environ.get(name, "1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _repo_dirty_summary(repo_root: Path) -> dict[str, Any]:
    def _run(args: list[str]) -> list[str]:
        run = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            check=False,
        )
        if run.returncode != 0:
            return []
        return [row.strip() for row in (run.stdout or "").splitlines() if row.strip()]

    unstaged = _run(["diff", "--name-only"])
    untracked = _run(["ls-files", "--others", "--exclude-standard"])
    return {
        "dirty_b": bool(unstaged or untracked),
        "unstaged_count_u64": int(len(unstaged)),
        "untracked_count_u64": int(len(untracked)),
        "unstaged_preview": [str(row) for row in unstaged[:10]],
        "untracked_preview": [str(row) for row in untracked[:10]],
    }


def main() -> None:
    ap = argparse.ArgumentParser(prog="preflight_long_run_v1")
    ap.add_argument("--campaign_pack", default=DEFAULT_PACK)
    ap.add_argument("--run_root", default=DEFAULT_RUN_ROOT)
    ap.add_argument("--summary_path", default=DEFAULT_SUMMARY)
    ap.add_argument("--start_tick_u64", type=int, default=1)
    ap.add_argument("--max_disk_bytes", type=int, default=DEFAULT_MAX_DISK_BYTES)
    ap.add_argument("--no_clean", action="store_true")
    args = ap.parse_args()

    checks: list[dict[str, Any]] = []
    started_unix_s = int(time.time())
    campaign_pack_rel = str(args.campaign_pack)
    run_root_rel = str(args.run_root)
    run_root = (REPO_ROOT / run_root_rel).resolve()
    summary_path = (REPO_ROOT / str(args.summary_path)).resolve()
    campaign_pack = (REPO_ROOT / campaign_pack_rel).resolve()

    if not campaign_pack.exists():
        raise SystemExit(f"missing pack: {campaign_pack}")
    if not args.no_clean and run_root.exists():
        shutil.rmtree(run_root)

    pack = load_canon_dict(campaign_pack)
    pack_root = campaign_pack.parent
    profile = load_canon_dict(pack_root / str(pack.get("long_run_profile_rel")))
    registry = load_canon_dict(pack_root / str(pack.get("omega_capability_registry_rel")))
    mission_cfg = profile.get("mission")
    if not isinstance(mission_cfg, dict):
        raise SystemExit("invalid profile mission block")
    mission_rel = str(mission_cfg.get("mission_request_rel", "")).strip()
    if not mission_rel:
        raise SystemExit("empty mission_request_rel")
    mission_path = (REPO_ROOT / mission_rel).resolve()

    mission_backup_bytes: bytes | None = None
    mission_existed = mission_path.exists()
    if mission_existed and mission_path.is_file():
        mission_backup_bytes = mission_path.read_bytes()

    baseline_last_row: dict[str, Any] | None = None
    canary_row: dict[str, Any] | None = None

    try:
        activation_mode = str(os.environ.get("OMEGA_META_CORE_ACTIVATION_MODE", "simulate")).strip().lower() or "simulate"
        activation_ok = activation_mode == "simulate"
        _record_check(
            checks,
            check_id="activation_mode_guard",
            pass_b=activation_ok,
            reason_code="OK" if activation_ok else "LIVE_ACTIVATION_UNSAFE_FOR_LONG_RUN_VERIFIER",
            detail={
                "observed_mode": activation_mode,
                "required_mode": "simulate",
            },
        )

        dirty_summary = _repo_dirty_summary(REPO_ROOT)
        dirty_mode_enabled = _env_truthy("OMEGA_CCAP_ALLOW_DIRTY_TREE", default=True)
        dirty_guard_ok = (not bool(dirty_summary["dirty_b"])) or dirty_mode_enabled
        _record_check(
            checks,
            check_id="dirty_tree_guard",
            pass_b=dirty_guard_ok,
            reason_code="OK" if dirty_guard_ok else "DIRTY_TREE_WITH_STRICT_CCAP",
            detail={
                **dirty_summary,
                "planned_dirty_mode_enabled_b": bool(dirty_mode_enabled),
            },
        )

        frontier_cap_rows = profile.get("lanes", {}).get("frontier_capability_ids", [])
        cap_rows = registry.get("capabilities") if isinstance(registry.get("capabilities"), list) else []
        by_cap: dict[str, dict[str, Any]] = {}
        for row in cap_rows:
            if not isinstance(row, dict):
                continue
            capability_id = str(row.get("capability_id", "")).strip()
            if capability_id:
                by_cap[capability_id] = row
        missing_frontier_caps = [str(cap) for cap in frontier_cap_rows if str(cap) and str(cap) not in by_cap]
        enabled_frontier_caps = [cap for cap in _frontier_enabled_caps(profile, registry)]
        missing_pack_paths: list[str] = []
        frontier_with_promotion_path_u64 = 0
        for capability_id in enabled_frontier_caps:
            row = by_cap.get(capability_id) or {}
            pack_rel = str(row.get("campaign_pack_rel", "")).strip()
            if not pack_rel or not (REPO_ROOT / pack_rel).exists():
                missing_pack_paths.append(capability_id)
            promo_rel = str(row.get("promotion_bundle_rel", "")).strip()
            if promo_rel:
                frontier_with_promotion_path_u64 += 1
        frontier_registry_ok = (
            (not missing_frontier_caps)
            and bool(enabled_frontier_caps)
            and (not missing_pack_paths)
            and int(frontier_with_promotion_path_u64) > 0
        )
        _record_check(
            checks,
            check_id="frontier_registry_wiring",
            pass_b=frontier_registry_ok,
            reason_code="OK" if frontier_registry_ok else "FRONTIER_REGISTRY_INVALID",
            detail={
                "missing_frontier_capability_ids": missing_frontier_caps,
                "enabled_frontier_capability_ids": enabled_frontier_caps,
                "missing_campaign_pack_capability_ids": missing_pack_paths,
                "frontier_with_promotion_path_u64": int(frontier_with_promotion_path_u64),
            },
        )

        _write_json(mission_path, MISSION_PAYLOAD_A)

        baseline_proc = _run_harness(
            campaign_pack_rel=campaign_pack_rel,
            run_root_rel=run_root_rel,
            start_tick_u64=int(args.start_tick_u64),
            max_ticks=20,
            max_disk_bytes=int(args.max_disk_bytes),
            force_lane="BASELINE",
            force_eval=False,
        )
        rows_after_baseline = _read_tick_rows(run_root)
        baseline_ok = baseline_proc.returncode == 0 and len(rows_after_baseline) == 20
        if rows_after_baseline:
            baseline_last_row = rows_after_baseline[-1]
        _record_check(
            checks,
            check_id="baseline_20_ticks",
            pass_b=baseline_ok,
            reason_code="OK" if baseline_ok else "BASELINE_STAGE_FAILED",
            detail={
                "returncode": int(baseline_proc.returncode),
                "rows_u64": int(len(rows_after_baseline)),
            },
        )

        baseline_lane_ok = baseline_ok and all(str(row.get("lane_name", "")) == "BASELINE" for row in rows_after_baseline)
        _record_check(
            checks,
            check_id="baseline_lane_enforced",
            pass_b=baseline_lane_ok,
            reason_code="OK" if baseline_lane_ok else "BASELINE_LANE_MISMATCH",
            detail={"lane_names": sorted({str(row.get("lane_name", "")) for row in rows_after_baseline})},
        )

        _write_json(mission_path, MISSION_PAYLOAD_B)
        canary_proc = _run_harness(
            campaign_pack_rel=campaign_pack_rel,
            run_root_rel=run_root_rel,
            start_tick_u64=None,
            max_ticks=1,
            max_disk_bytes=int(args.max_disk_bytes),
            force_lane="CANARY",
            force_eval=True,
        )
        rows_after_canary = _read_tick_rows(run_root)
        if rows_after_canary:
            canary_row = rows_after_canary[-1]
        canary_ok = (
            canary_proc.returncode == 0
            and len(rows_after_canary) >= 21
            and canary_row is not None
            and str(canary_row.get("lane_name", "")) == "CANARY"
        )
        _record_check(
            checks,
            check_id="canary_tick",
            pass_b=canary_ok,
            reason_code="OK" if canary_ok else "CANARY_STAGE_FAILED",
            detail={
                "returncode": int(canary_proc.returncode),
                "rows_u64": int(len(rows_after_canary)),
                "lane_name": str((canary_row or {}).get("lane_name", "")),
            },
        )

        mission_change_ok = False
        mission_detail: dict[str, Any] = {}
        if baseline_last_row is not None and canary_row is not None:
            baseline_state = Path(str(baseline_last_row.get("state_dir", "")))
            canary_state = Path(str(canary_row.get("state_dir", "")))
            baseline_mission_receipt, _ = _latest_payload(
                baseline_state / "long_run" / "mission",
                "mission_goal_ingest_receipt_v1.json",
            )
            canary_mission_receipt, _ = _latest_payload(
                canary_state / "long_run" / "mission",
                "mission_goal_ingest_receipt_v1.json",
            )
            if isinstance(baseline_mission_receipt, dict) and isinstance(canary_mission_receipt, dict):
                mission_change_ok = (
                    str(baseline_mission_receipt.get("mission_hash", "")).strip()
                    != str(canary_mission_receipt.get("mission_hash", "")).strip()
                    and str(canary_mission_receipt.get("status", "")).strip() == "MISSION_GOAL_ADDED"
                )
                mission_detail = {
                    "baseline_status": str(baseline_mission_receipt.get("status", "")),
                    "baseline_hash": str(baseline_mission_receipt.get("mission_hash", "")),
                    "canary_status": str(canary_mission_receipt.get("status", "")),
                    "canary_hash": str(canary_mission_receipt.get("mission_hash", "")),
                }
        _record_check(
            checks,
            check_id="mission_mutation_receipt",
            pass_b=mission_change_ok,
            reason_code="OK" if mission_change_ok else "MISSION_MUTATION_NOT_OBSERVED",
            detail=mission_detail,
        )

        eval_ok = canary_row is not None and bool(str(canary_row.get("eval_report_hash", "")).strip())
        _record_check(
            checks,
            check_id="eval_report_presence",
            pass_b=eval_ok,
            reason_code="OK" if eval_ok else "EVAL_REPORT_MISSING",
            detail={"eval_report_hash": str((canary_row or {}).get("eval_report_hash", ""))},
        )

        frontier_caps = _frontier_enabled_caps(profile, registry)
        frontier_health_pass = False
        frontier_health_counts = {
            "invalid_count_u64": 0,
            "budget_exhaust_count_u64": 0,
            "route_disabled_count_u64": 0,
        }
        if canary_row is not None:
            frontier_health_pass, frontier_health_counts = _health_gate_from_state(
                Path(str(canary_row.get("state_dir", ""))),
                profile,
            )
        frontier_should_run = bool(frontier_caps) and bool(frontier_health_pass)
        if frontier_should_run:
            frontier_proc = _run_harness(
                campaign_pack_rel=campaign_pack_rel,
                run_root_rel=run_root_rel,
                start_tick_u64=None,
                max_ticks=3,
                max_disk_bytes=int(args.max_disk_bytes),
                force_lane="FRONTIER",
                force_eval=False,
            )
            rows_after_frontier = _read_tick_rows(run_root)
            frontier_rows = [row for row in rows_after_frontier if str(row.get("lane_name", "")) == "FRONTIER"]
            frontier_row = frontier_rows[-1] if frontier_rows else None
            frontier_ok = (
                frontier_proc.returncode == 0
                and frontier_row is not None
                and str(frontier_row.get("lane_name", "")) == "FRONTIER"
            )
            _record_check(
                checks,
                check_id="frontier_tick_optional",
                pass_b=frontier_ok,
                reason_code="OK" if frontier_ok else "FRONTIER_STAGE_FAILED",
                detail={
                    "returncode": int(frontier_proc.returncode),
                    "lane_name": str((frontier_row or {}).get("lane_name", "")),
                    "frontier_rows_u64": int(len(frontier_rows)),
                    "enabled_frontier_capability_ids": frontier_caps,
                    "health_counts": frontier_health_counts,
                },
            )
        else:
            _record_check(
                checks,
                check_id="frontier_tick_optional",
                pass_b=True,
                reason_code="FRONTIER_SKIPPED",
                detail={
                    "enabled_frontier_capability_ids": frontier_caps,
                    "health_gate_pass_b": bool(frontier_health_pass),
                    "health_counts": frontier_health_counts,
                },
            )

        all_rows = _read_tick_rows(run_root)
        replay_invalid_ticks_from_harness = [
            int(row.get("tick_u64", -1))
            for row in all_rows
            if bool(row.get("state_verifier_valid_b")) is not True
        ]
        replay_invalid_ticks_head: list[int] = []
        replay_head_reason = ""
        if all_rows:
            head_row = all_rows[-1]
            head_tick_u64 = int(head_row.get("tick_u64", -1))
            head_state_dir = Path(str(head_row.get("state_dir", "")))
            head_ok, head_verify_out = _verify_state(head_state_dir)
            if not head_ok:
                replay_invalid_ticks_head.append(head_tick_u64)
                replay_head_reason = head_verify_out
        replay_invalid_ticks = sorted({*replay_invalid_ticks_from_harness, *replay_invalid_ticks_head})
        replay_ok = len(replay_invalid_ticks) == 0
        _record_check(
            checks,
            check_id="replay_window_valid",
            pass_b=replay_ok,
            reason_code="OK" if replay_ok else "REPLAY_INVALID",
            detail={
                "invalid_ticks": replay_invalid_ticks,
                "invalid_ticks_from_harness": replay_invalid_ticks_from_harness,
                "invalid_ticks_head_recheck": replay_invalid_ticks_head,
                "head_recheck_reason": replay_head_reason,
            },
        )

        canary_files = sorted((run_root / "canary").glob("sha256_*.long_run_canary_summary_v1.json"))
        canary_ok = len(canary_files) >= 1
        _record_check(
            checks,
            check_id="canary_summary_present",
            pass_b=canary_ok,
            reason_code="OK" if canary_ok else "CANARY_SUMMARY_MISSING",
            detail={"count_u64": int(len(canary_files))},
        )

        pruned_ticks = _read_pruned_ticks(run_root)
        head_payload = _load_json(run_root / "index" / HEAD_NAME)
        head_tick = int(head_payload.get("tick_u64", -1))
        all_ticks = [int(row.get("tick_u64", -1)) for row in all_rows]
        last_tick = max(all_ticks) if all_ticks else -1
        head_ok = head_tick == last_tick
        _record_check(
            checks,
            check_id="index_head_consistent",
            pass_b=head_ok,
            reason_code="OK" if head_ok else "INDEX_HEAD_MISMATCH",
            detail={"head_tick_u64": head_tick, "last_tick_u64": last_tick},
        )

        disk_policy_ok = True
        live_disk_bytes = 0
        for row in all_rows:
            tick_u64 = int(row.get("tick_u64", -1))
            out_dir = Path(str(row.get("out_dir", "")))
            disk_bytes = int(max(0, int(row.get("disk_bytes_u64", 0))))
            if tick_u64 in pruned_ticks:
                if out_dir.exists():
                    disk_policy_ok = False
            else:
                if not out_dir.exists():
                    disk_policy_ok = False
                live_disk_bytes += disk_bytes
        if live_disk_bytes > int(args.max_disk_bytes):
            disk_policy_ok = False
        _record_check(
            checks,
            check_id="disk_index_policy",
            pass_b=disk_policy_ok,
            reason_code="OK" if disk_policy_ok else "DISK_INDEX_POLICY_FAIL",
            detail={
                "live_disk_bytes_u64": int(live_disk_bytes),
                "max_disk_bytes_u64": int(args.max_disk_bytes),
                "pruned_tick_count_u64": int(len(pruned_ticks)),
            },
        )

        explicit_reasons_ok = True
        opaque_hits: list[str] = []
        for row in all_rows:
            reason = str(row.get("promotion_reason_code", "")).strip()
            if reason and _is_opaque_reason(reason):
                explicit_reasons_ok = False
                opaque_hits.append(f"tick:{int(row.get('tick_u64', -1))}:promotion:{reason}")
            state_dir = Path(str(row.get("state_dir", "")))
            mission_receipt, _ = _latest_payload(state_dir / "long_run" / "mission", "mission_goal_ingest_receipt_v1.json")
            lane_receipt, _ = _latest_payload(state_dir / "long_run" / "lane", "lane_decision_receipt_v1.json")
            if isinstance(mission_receipt, dict):
                m_reason = str(mission_receipt.get("reason_code", "")).strip()
                if (not m_reason) or _is_opaque_reason(m_reason):
                    explicit_reasons_ok = False
                    opaque_hits.append(f"tick:{int(row.get('tick_u64', -1))}:mission:{m_reason or 'empty'}")
            if isinstance(lane_receipt, dict):
                lane_reasons = lane_receipt.get("reason_codes")
                if not isinstance(lane_reasons, list) or not lane_reasons:
                    explicit_reasons_ok = False
                    opaque_hits.append(f"tick:{int(row.get('tick_u64', -1))}:lane:empty")
                else:
                    for lane_reason in lane_reasons:
                        if _is_opaque_reason(lane_reason):
                            explicit_reasons_ok = False
                            opaque_hits.append(f"tick:{int(row.get('tick_u64', -1))}:lane:{lane_reason}")
        _record_check(
            checks,
            check_id="explicit_reason_codes",
            pass_b=explicit_reasons_ok,
            reason_code="OK" if explicit_reasons_ok else "OPAQUE_REASON_CODE_FOUND",
            detail={"hits": opaque_hits},
        )

        frontier_rows = [row for row in all_rows if str(row.get("lane_name", "")) == "FRONTIER"]
        frontier_counted_ticks = [int(row.get("tick_u64", -1)) for row in frontier_rows if bool(row.get("frontier_attempt_counted_b", False))]
        frontier_signal_ok = (not frontier_rows) or bool(frontier_counted_ticks)
        _record_check(
            checks,
            check_id="frontier_attempt_signal",
            pass_b=frontier_signal_ok,
            reason_code="OK" if frontier_signal_ok else "NO_COUNTED_FRONTIER_ATTEMPT",
            detail={
                "frontier_ticks_u64": int(len(frontier_rows)),
                "counted_frontier_ticks": frontier_counted_ticks,
            },
        )

        invalid_ticks = [int(row.get("tick_u64", -1)) for row in all_rows if str(row.get("subverifier_status", "")).strip().upper() == "INVALID"]
        blocking_invalid_ticks = [
            int(row.get("tick_u64", -1))
            for row in all_rows
            if str(row.get("subverifier_status", "")).strip().upper() == "INVALID"
            and not (
                str(row.get("action_kind", "")).strip() == "SAFE_HALT"
                and not bool(row.get("candidate_bundle_present_b", False))
            )
        ]
        subverifier_ok = len(blocking_invalid_ticks) == 0
        _record_check(
            checks,
            check_id="subverifier_invalid_guard",
            pass_b=subverifier_ok,
            reason_code="OK" if subverifier_ok else "SUBVERIFIER_INVALID_PRESENT",
            detail={
                "invalid_ticks": invalid_ticks,
                "blocking_invalid_ticks": blocking_invalid_ticks,
            },
        )

        frontier_no_bundle_ticks = [
            int(row.get("tick_u64", -1))
            for row in frontier_rows
            if str(row.get("promotion_reason_code", "")).strip() == "NO_PROMOTION_BUNDLE"
        ]
        frontier_candidate_bundle_ticks = [
            int(row.get("tick_u64", -1))
            for row in frontier_rows
            if bool(row.get("candidate_bundle_present_b", False))
        ]
        frontier_promoted_ticks = [
            int(row.get("tick_u64", -1))
            for row in frontier_rows
            if str(row.get("promotion_status", "")).strip() == "PROMOTED"
        ]
        frontier_promotion_pipeline_ok = (not frontier_rows) or bool(frontier_candidate_bundle_ticks or frontier_promoted_ticks)
        _record_check(
            checks,
            check_id="frontier_promotion_pipeline_signal",
            pass_b=frontier_promotion_pipeline_ok,
            reason_code="OK" if frontier_promotion_pipeline_ok else "NO_PROMOTION_PIPELINE_SIGNAL",
            detail={
                "frontier_ticks_u64": int(len(frontier_rows)),
                "frontier_no_promotion_bundle_ticks": frontier_no_bundle_ticks,
                "frontier_candidate_bundle_ticks": frontier_candidate_bundle_ticks,
                "frontier_promoted_ticks": frontier_promoted_ticks,
            },
        )
    finally:
        if mission_backup_bytes is not None:
            mission_path.parent.mkdir(parents=True, exist_ok=True)
            mission_path.write_bytes(mission_backup_bytes)
        elif mission_existed:
            if mission_path.is_file():
                mission_path.unlink(missing_ok=True)
        else:
            if mission_path.is_file():
                mission_path.unlink(missing_ok=True)

    pass_b = all(bool(row.get("pass_b", False)) for row in checks)
    summary: dict[str, Any] = {
        "schema_name": "long_run_preflight_summary_v1",
        "schema_version": "v1",
        "summary_id": "sha256:" + ("0" * 64),
        "started_unix_s": int(started_unix_s),
        "finished_unix_s": int(time.time()),
        "campaign_pack_rel": campaign_pack_rel,
        "run_root_rel": run_root_rel,
        "pass_b": bool(pass_b),
        "checks": checks,
    }
    summary["summary_id"] = canon_hash_obj({k: v for k, v in summary.items() if k != "summary_id"})
    _write_json(summary_path, summary)
    print(str(summary_path))
    print("PASS" if pass_b else "FAIL")
    raise SystemExit(0 if pass_b else 1)


if __name__ == "__main__":
    main()
