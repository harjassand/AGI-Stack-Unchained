#!/usr/bin/env python3
"""Deterministic long-run harness with index-backed resume and pruning."""

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
from cdel.v18_0.omega_ledger_v1 import append_event, load_ledger
from cdel.v19_0.common_v1 import validate_schema as validate_schema_v19


TICK_INDEX_NAME = "long_run_tick_index_v1.jsonl"
PRUNE_INDEX_NAME = "long_run_prune_index_v1.jsonl"
HEAD_NAME = "long_run_head_v1.json"
ENV_RECEIPT_NAME = "run_env_receipt_v1.json"
LAUNCH_MANIFEST_NAME = "long_run_launch_manifest_v1.json"
LAUNCH_BINDING_MARKER_NAME = "long_run_launch_manifest_binding_v1.json"
STOP_RECEIPT_NAME = "LONG_RUN_STOP_RECEIPT_v1.json"
LANE_RECEIPT_FINAL_NAME = "lane_receipt_final.long_run_lane_v1.json"
ORPHAN_EK_RUNS_NOTE_NAME = "CLEANUP_ORPHAN_EK_RUNS_V1.json"
ORPHAN_EK_RUNS_LOG_NAME = "long_run_orphan_ek_runs_cleanup_v1.jsonl"

DEFAULT_PACK = "campaigns/rsi_omega_daemon_v19_0_long_run_v1/rsi_omega_daemon_pack_v1.json"
DEFAULT_RUN_ROOT = "runs/long_disciplined_v1"
DEFAULT_MAX_DISK_BYTES = 20 * 1024 * 1024 * 1024
DEFAULT_RETAIN_LAST = 200
DEFAULT_ANCHOR_EVERY = 100
DEFAULT_CANARY_EVERY = 10
DEFAULT_HIST_WINDOW = 50
MANDATORY_FRONTIER_GOALS_DEADLINE_TICK_U64 = 20
MANDATORY_HARD_LOCK_DEADLINE_TICK_U64 = 40
MANDATORY_COUNTED_FRONTIER_DEADLINE_TICK_U64 = 60
MANDATORY_FORCED_HEAVY_SH1_DEADLINE_TICK_U64 = 60
MANDATORY_FORCED_HEAVY_SH1_MIN_TICKS_U64 = 1
EARLY_GOODHART_MIN_TICK_U64 = 30
EARLY_GOODHART_MAX_TICK_U64 = 40
GOODHART_PROMOTION_FARM_LIMIT_U64 = 50
GOODHART_FRONTIER_GAMING_DEADLINE_TICK_U64 = 200
GOODHART_FRONTIER_GAMING_MIN_COUNTED_U64 = 5
QUALITY_WINDOW_SHORT_U64 = 50
QUALITY_WINDOW_LONG_U64 = 200
FRONTIER_ATTEMPT_QUALITY_VALID_BUT_NO_UTILITY = "FRONTIER_ATTEMPT_VALID_BUT_NO_UTILITY"
FRONTIER_ATTEMPT_QUALITY_INVALID = "FRONTIER_ATTEMPT_INVALID"
FRONTIER_ATTEMPT_QUALITY_HEAVY_OK = "FRONTIER_ATTEMPT_HEAVY_OK"
FRONTIER_DISPATCH_PRE_EVIDENCE_REASON_CODE = "FRONTIER_DISPATCH_FAILED_PRE_EVIDENCE"

ENV_ALLOWLIST = (
    "PYTHONPATH",
    "OMEGA_NET_LIVE_OK",
    "OMEGA_META_CORE_ACTIVATION_MODE",
    "OMEGA_ALLOW_SIMULATE_ACTIVATION",
    "OMEGA_CCAP_ALLOW_DIRTY_TREE",
    "OMEGA_CCAP_CPU_MS_MAX",
    "OMEGA_CCAP_WALL_MS_MAX",
    "OMEGA_CCAP_MEM_MB_MAX",
    "OMEGA_CCAP_DISK_MB_MAX",
    "OMEGA_CCAP_FDS_MAX",
    "OMEGA_CCAP_PROCS_MAX",
    "OMEGA_CCAP_THREADS_MAX",
    "OMEGA_BLACKBOX",
    "OMEGA_DISABLE_FORCED_RUNAWAY",
    "OMEGA_RUN_SEED_U64",
    "OMEGA_LONG_RUN_FORCE_LANE",
    "OMEGA_LONG_RUN_FORCE_EVAL",
    "OMEGA_LONG_RUN_LAUNCH_MANIFEST_HASH",
    "OMEGA_LONG_RUN_LOOP_BREAKER_SCOPE_MODE",
    "OMEGA_LONG_VALIDATE_FRONTIER",
    "OMEGA_LONG_VALIDATE_WINDOW_TICKS",
    "OMEGA_LONG_VALIDATE_MIN_HARDLOCKS",
    "OMEGA_LONG_VALIDATE_MIN_FORCED",
    "OMEGA_LONG_VALIDATE_MIN_COUNTED",
    "OMEGA_LONG_VALIDATE_FORCED_HEAVY_SH1_DEADLINE_TICK_U64",
    "OMEGA_LONG_VALIDATE_FORCED_HEAVY_SH1_MIN_TICKS_U64",
    "OMEGA_PREMARATHON_V63",
    "OMEGA_MILESTONE_FORCE_SH1_FRONTIER_B",
    "OMEGA_RETENTION_PRUNE_CCAP_EK_RUNS_B",
    "OMEGA_SH1_FORCED_HEAVY_B",
    "OMEGA_SH1_FORCED_DEBT_KEY",
    "OMEGA_SH1_WIRING_LOCUS_RELPATH",
    "ORCH_LLM_BACKEND",
)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canon_bytes(payload) + b"\n")


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        handle.write(canon_bytes(payload) + b"\n")


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


def _env_bool(name: str, *, default: bool = False) -> bool:
    raw = str(os.environ.get(name, "1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _premarathon_v63_enabled() -> bool:
    return _env_bool("OMEGA_PREMARATHON_V63", default=False)


def _env_u64(name: str, *, default: int, minimum: int = 0) -> int:
    raw = str(os.environ.get(name, str(int(default)))).strip()
    value = int(raw)
    return int(max(int(minimum), value))


def _is_sha256(value: Any) -> bool:
    text = str(value).strip()
    return text.startswith("sha256:") and len(text) == 71 and all(ch in "0123456789abcdef" for ch in text.split(":", 1)[1])


def _count_true(rows: list[dict[str, Any]], key: str) -> int:
    return int(sum(1 for row in rows if row.get(key) is True))


def _count_promoted(rows: list[dict[str, Any]]) -> int:
    return int(
        sum(
            1
            for row in rows
            if str(row.get("promotion_status", "")).strip().upper() == "PROMOTED"
        )
    )


def _count_quality_class(rows: list[dict[str, Any]], quality_class: str) -> int:
    return int(
        sum(
            1
            for row in rows
            if str(row.get("frontier_attempt_quality_class", "")).strip() == str(quality_class)
        )
    )


def _frontier_attempt_quality_class_for_row(row: dict[str, Any]) -> str | None:
    if row.get("frontier_attempt_counted_b") is not True:
        return None
    effect_class = str(row.get("effect_class", "")).strip().upper()
    subverifier_status = str(row.get("subverifier_status", "")).strip().upper()
    action_kind = str(row.get("action_kind", "")).strip().upper()
    state_verifier_reason_code = str(row.get("state_verifier_reason_code", "")).strip().upper()
    promotion_reason_code = str(row.get("promotion_reason_code", "")).strip().upper()
    subverifier_reason_code = str(row.get("subverifier_reason_code", "")).strip().upper()
    status = str(row.get("status", "")).strip().upper()
    if effect_class == "EFFECT_HEAVY_OK":
        return FRONTIER_ATTEMPT_QUALITY_HEAVY_OK
    if effect_class == "EFFECT_HEAVY_NO_UTILITY":
        return FRONTIER_ATTEMPT_QUALITY_VALID_BUT_NO_UTILITY
    if (
        subverifier_status == "INVALID"
        or action_kind == "SAFE_HALT"
        or state_verifier_reason_code == "SCHEMA_FAIL"
        or promotion_reason_code == "SCHEMA_FAIL"
        or subverifier_reason_code == "SCHEMA_FAIL"
        or status != "OK"
    ):
        return FRONTIER_ATTEMPT_QUALITY_INVALID
    return FRONTIER_ATTEMPT_QUALITY_INVALID


def _frontier_attempt_quality_counts(*, rows: list[dict[str, Any]], window_u64: int | None = None) -> dict[str, int]:
    if window_u64 is None:
        scope = list(rows)
    else:
        scope = list(rows[-int(max(1, int(window_u64))) :])
    return {
        "rows_u64": int(len(scope)),
        "frontier_counted_total_u64": int(_count_true(scope, "frontier_attempt_counted_b")),
        "frontier_attempt_heavy_ok_total_u64": int(_count_quality_class(scope, FRONTIER_ATTEMPT_QUALITY_HEAVY_OK)),
        "frontier_attempt_valid_but_no_utility_total_u64": int(
            _count_quality_class(scope, FRONTIER_ATTEMPT_QUALITY_VALID_BUT_NO_UTILITY)
        ),
        "frontier_attempt_invalid_total_u64": int(_count_quality_class(scope, FRONTIER_ATTEMPT_QUALITY_INVALID)),
    }


def _attach_frontier_attempt_quality_telemetry(*, rows: list[dict[str, Any]], row: dict[str, Any]) -> None:
    quality_class = _frontier_attempt_quality_class_for_row(row)
    row["frontier_attempt_quality_class"] = quality_class
    combined = [*rows, row]
    row["frontier_attempt_quality_counts_total"] = _frontier_attempt_quality_counts(rows=combined, window_u64=None)
    row["frontier_attempt_quality_counts_last_50"] = _frontier_attempt_quality_counts(
        rows=combined,
        window_u64=QUALITY_WINDOW_SHORT_U64,
    )
    row["frontier_attempt_quality_counts_last_200"] = _frontier_attempt_quality_counts(
        rows=combined,
        window_u64=QUALITY_WINDOW_LONG_U64,
    )


def _attach_hard_lock_transition_telemetry(*, rows: list[dict[str, Any]], row: dict[str, Any]) -> None:
    prev_hard_lock_active_b = bool(rows[-1].get("hard_lock_active_b")) if rows else False
    hard_lock_active_b = bool(row.get("hard_lock_active_b"))
    hard_lock_became_active_b = bool((not prev_hard_lock_active_b) and hard_lock_active_b)
    frontier_counted_b = bool(row.get("frontier_attempt_counted_b"))
    declared_class = str(row.get("declared_class", "")).strip().upper()
    selected_frontier_b = declared_class == "FRONTIER_HEAVY"
    transition_failed_b = bool(hard_lock_became_active_b and ((not selected_frontier_b) or (not frontier_counted_b)))
    pre_evidence_failed_b = bool(row.get("frontier_dispatch_failed_pre_evidence_b")) or transition_failed_b
    row["hard_lock_became_active_b"] = hard_lock_became_active_b
    row["hard_lock_selected_frontier_b"] = selected_frontier_b
    row["frontier_dispatch_failed_pre_evidence_b"] = pre_evidence_failed_b
    row["frontier_dispatch_pre_evidence_reason_code"] = (
        FRONTIER_DISPATCH_PRE_EVIDENCE_REASON_CODE if pre_evidence_failed_b else None
    )


def _axis_gate_rejection_counts(*, rows: list[dict[str, Any]], window_u64: int | None = None) -> tuple[int, dict[str, int]]:
    if window_u64 is None:
        scope = list(rows)
    else:
        scope = list(rows[-int(max(1, int(window_u64))) :])
    reason_counts: dict[str, int] = {}
    rejected_u64 = 0
    for row in scope:
        reason = str(row.get("axis_gate_reason_code", "NONE")).strip().upper() or "NONE"
        if reason == "NONE":
            continue
        rejected_u64 += 1
        reason_counts[reason] = int(reason_counts.get(reason, 0) + 1)
    return int(rejected_u64), {key: int(reason_counts[key]) for key in sorted(reason_counts.keys())}


def _attach_axis_gate_telemetry(*, rows: list[dict[str, Any]], row: dict[str, Any]) -> None:
    combined = [*rows, row]
    rejected_u64, reason_counts = _axis_gate_rejection_counts(rows=combined, window_u64=None)
    row["axis_gate_rejected_u64"] = int(rejected_u64)
    row["axis_gate_reason_code_counts"] = reason_counts


def _heavy_success_counts(*, rows: list[dict[str, Any]], window_u64: int | None = None) -> dict[str, int]:
    if window_u64 is None:
        scope = list(rows)
    else:
        scope = list(rows[-int(max(1, int(window_u64))) :])
    utility_ok_u64 = int(sum(1 for row in scope if row.get("heavy_utility_ok_b") is True))
    promoted_u64 = int(sum(1 for row in scope if row.get("heavy_promoted_b") is True))
    return {
        "rows_u64": int(len(scope)),
        "heavy_utility_ok_u64": int(utility_ok_u64),
        "heavy_promoted_u64": int(promoted_u64),
    }


def _attach_heavy_success_telemetry(*, rows: list[dict[str, Any]], row: dict[str, Any]) -> None:
    combined = [*rows, row]
    row["heavy_success_counts_total"] = _heavy_success_counts(rows=combined, window_u64=None)
    row["heavy_success_counts_last_50"] = _heavy_success_counts(rows=combined, window_u64=QUALITY_WINDOW_SHORT_U64)
    row["heavy_success_counts_last_200"] = _heavy_success_counts(rows=combined, window_u64=QUALITY_WINDOW_LONG_U64)


def _mandatory_frontier_guard_summary(*, rows: list[dict[str, Any]]) -> dict[str, int]:
    quality_counts_total = _frontier_attempt_quality_counts(rows=rows, window_u64=None)
    return {
        "rows_u64": int(len(rows)),
        "frontier_total_u64": int(_count_true(rows, "frontier_goals_pending_b")),
        "hard_locks_total_u64": int(_count_true(rows, "hard_lock_active_b")),
        "frontier_counted_total_u64": int(quality_counts_total["frontier_counted_total_u64"]),
        "frontier_attempt_heavy_ok_total_u64": int(quality_counts_total["frontier_attempt_heavy_ok_total_u64"]),
        "frontier_attempt_valid_but_no_utility_total_u64": int(
            quality_counts_total["frontier_attempt_valid_but_no_utility_total_u64"]
        ),
        "frontier_attempt_invalid_total_u64": int(quality_counts_total["frontier_attempt_invalid_total_u64"]),
        "forced_heavy_sh1_total_u64": int(_count_true(rows, "forced_heavy_sh1_b")),
        "promoted_u64": int(_count_promoted(rows)),
    }


def _mandatory_frontier_guard_reason(
    *,
    rows: list[dict[str, Any]],
    tick_u64: int,
) -> tuple[str | None, dict[str, Any]]:
    tick_value = int(max(0, int(tick_u64)))
    summary = _mandatory_frontier_guard_summary(rows=rows)
    detail: dict[str, Any] = {
        "tick_u64": int(tick_value),
        "deadlines_u64": {
            "frontier_goals_deadline_u64": int(MANDATORY_FRONTIER_GOALS_DEADLINE_TICK_U64),
            "hard_lock_deadline_u64": int(MANDATORY_HARD_LOCK_DEADLINE_TICK_U64),
            "frontier_counted_deadline_u64": int(MANDATORY_COUNTED_FRONTIER_DEADLINE_TICK_U64),
            "forced_heavy_sh1_deadline_u64": int(MANDATORY_FORCED_HEAVY_SH1_DEADLINE_TICK_U64),
        },
        **summary,
    }
    if (
        int(EARLY_GOODHART_MIN_TICK_U64) <= tick_value <= int(EARLY_GOODHART_MAX_TICK_U64)
        and int(summary["frontier_total_u64"]) == 0
        and int(summary["promoted_u64"]) > 0
    ):
        return "PRECHECK_FAIL:PROMOTION_WITHOUT_FRONTIER_GOALS", detail
    if (
        int(summary["promoted_u64"]) >= int(GOODHART_PROMOTION_FARM_LIMIT_U64)
        and int(summary["hard_locks_total_u64"]) == 0
    ):
        return "PRECHECK_FAIL:GOODHART_BYPASS_PROMOTION_FARM", detail
    if (
        tick_value >= int(GOODHART_FRONTIER_GAMING_DEADLINE_TICK_U64)
        and int(summary["frontier_counted_total_u64"]) >= int(GOODHART_FRONTIER_GAMING_MIN_COUNTED_U64)
        and int(summary["frontier_attempt_heavy_ok_total_u64"]) == 0
    ):
        detail["frontier_gaming_limits_u64"] = {
            "min_counted_u64": int(GOODHART_FRONTIER_GAMING_MIN_COUNTED_U64),
            "deadline_tick_u64": int(GOODHART_FRONTIER_GAMING_DEADLINE_TICK_U64),
        }
        return "PRECHECK_FAIL:FRONTIER_GAMING_NO_HEAVY_OK", detail
    if (
        tick_value >= int(MANDATORY_FRONTIER_GOALS_DEADLINE_TICK_U64)
        and int(summary["frontier_total_u64"]) == 0
    ):
        return "PRECHECK_FAIL:NO_FRONTIER_GOALS_PRESENT", detail
    if (
        tick_value >= int(MANDATORY_HARD_LOCK_DEADLINE_TICK_U64)
        and int(summary["hard_locks_total_u64"]) == 0
    ):
        return "PRECHECK_FAIL:NO_HARD_LOCK", detail
    if (
        _premarathon_v63_enabled()
        and _env_bool("OMEGA_PREMARATHON_REQUIRE_FORCED_HEAVY_SH1", default=False)
        and (
        tick_value >= int(MANDATORY_FORCED_HEAVY_SH1_DEADLINE_TICK_U64)
        and int(summary["forced_heavy_sh1_total_u64"]) < int(MANDATORY_FORCED_HEAVY_SH1_MIN_TICKS_U64)
        )
    ):
        detail["forced_heavy_sh1_min_ticks_u64"] = int(MANDATORY_FORCED_HEAVY_SH1_MIN_TICKS_U64)
        return "PRECHECK_FAIL:NO_FORCED_HEAVY_SH1", detail
    if (
        tick_value >= int(MANDATORY_COUNTED_FRONTIER_DEADLINE_TICK_U64)
        and int(summary["frontier_counted_total_u64"]) == 0
    ):
        return "PRECHECK_FAIL:NO_COUNTED_FRONTIER_ATTEMPT", detail
    return None, detail


def _frontier_precheck_summary(
    *,
    rows: list[dict[str, Any]],
    window_ticks_u64: int,
    min_hardlocks_u64: int,
    min_forced_u64: int,
    min_counted_u64: int,
) -> dict[str, Any]:
    tail = list(rows[-int(max(1, window_ticks_u64)) :])
    hardlocks = _count_true(tail, "hard_lock_active_b")
    forced = _count_true(tail, "forced_frontier_attempt_b")
    counted = _count_true(tail, "frontier_attempt_counted_b")
    return {
        "window_rows_u64": int(len(tail)),
        "hard_lock_count_u64": int(hardlocks),
        "forced_frontier_count_u64": int(forced),
        "counted_frontier_attempt_count_u64": int(counted),
        "min_hard_locks_u64": int(min_hardlocks_u64),
        "min_forced_u64": int(min_forced_u64),
        "min_counted_u64": int(min_counted_u64),
    }


def _frontier_precheck_reason(summary: dict[str, Any]) -> tuple[str | None, list[str]]:
    missing: list[str] = []
    if int(summary.get("hard_lock_count_u64", 0)) < int(summary.get("min_hard_locks_u64", 0)):
        missing.append("hard_lock")
    if int(summary.get("forced_frontier_count_u64", 0)) < int(summary.get("min_forced_u64", 0)):
        missing.append("forced_frontier")
    if int(summary.get("counted_frontier_attempt_count_u64", 0)) < int(summary.get("min_counted_u64", 0)):
        missing.append("counted_frontier_attempt")
    if "hard_lock" in missing:
        return "PRECHECK_FAIL:NO_HARD_LOCK", missing
    if "forced_frontier" in missing:
        return "PRECHECK_FAIL:NO_FORCED_FRONTIER", missing
    if "counted_frontier_attempt" in missing:
        return "PRECHECK_FAIL:NO_COUNTED_FRONTIER_ATTEMPT", missing
    return None, missing


def _dir_size_bytes(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            file_path = Path(root) / name
            try:
                total += int(file_path.stat().st_size)
            except FileNotFoundError:
                continue
    return int(total)


def _latest_payload(dir_path: Path, suffix: str) -> tuple[dict[str, Any] | None, str | None]:
    if not dir_path.exists() or not dir_path.is_dir():
        return None, None
    rows = sorted(dir_path.glob(f"sha256_*.{suffix}"), key=lambda p: p.as_posix())
    if not rows:
        return None, None
    payload = load_canon_dict(rows[-1])
    digest = "sha256:" + rows[-1].name.split(".", 1)[0].split("_", 1)[1]
    return payload, digest


def _lane_receipt_final_payload(state_dir: Path) -> tuple[dict[str, Any] | None, str | None]:
    path = state_dir / "long_run" / "lane" / LANE_RECEIPT_FINAL_NAME
    if not path.exists() or not path.is_file():
        return None, None
    payload = load_canon_dict(path)
    if not isinstance(payload, dict):
        return None, None
    if str(payload.get("schema_name", "")).strip() != "lane_decision_receipt_v1":
        return None, None
    return payload, canon_hash_obj(payload)


def _metric_q32(metrics: dict[str, Any] | None, metric_id: str, *, fallback_metric_id: str | None = None) -> int:
    if not isinstance(metrics, dict):
        return 0
    value = metrics.get(metric_id)
    if value is None and isinstance(fallback_metric_id, str):
        value = metrics.get(fallback_metric_id)
    if isinstance(value, dict) and set(value.keys()) == {"q"}:
        return int(value.get("q", 0))
    if isinstance(value, int):
        return int(value)
    return 0


def _canonical_axis_gate_relpath(path_value: Any) -> str:
    raw = str(path_value).strip().replace("\\", "/")
    parts: list[str] = []
    for token in raw.split("/"):
        part = str(token).strip()
        if not part or part == ".":
            continue
        if part == "..":
            return ""
        parts.append(part)
    if not parts:
        return ""
    return "/".join(parts)


def _canonical_axis_gate_relpaths(rows: Any) -> list[str]:
    if not isinstance(rows, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for row in rows:
        rel = _canonical_axis_gate_relpath(row)
        if not rel:
            continue
        if rel not in seen:
            out.append(rel)
            seen.add(rel)
    return sorted(out)


def _axis_gate_index_fields(*, state_dir: Path, promotion_reason_code: str | None = None) -> dict[str, Any]:
    out = {
        "axis_gate_required_b": False,
        "axis_gate_exempted_b": False,
        "axis_gate_reason_code": "NONE",
        "axis_gate_axis_id": None,
        "axis_gate_bundle_present_b": False,
        "axis_gate_bundle_sha256": None,
        "axis_gate_checked_relpaths_v1": [],
    }
    if state_dir.exists() and state_dir.is_dir():
        candidates = sorted(
            [
                *state_dir.glob("dispatch/*/promotion/axis_gate_failure_v1.json"),
                *state_dir.glob("subruns/*/promotion/axis_gate_failure_v1.json"),
            ],
            key=lambda row: row.as_posix(),
        )
        if candidates:
            payload = load_canon_dict(candidates[-1])
            if isinstance(payload, dict):
                out["axis_gate_required_b"] = bool(payload.get("axis_gate_required_b", False))
                out["axis_gate_exempted_b"] = bool(payload.get("axis_gate_exempted_b", False))
                reason_raw = str(payload.get("axis_gate_reason_code", "")).strip().upper()
                out["axis_gate_reason_code"] = reason_raw if reason_raw else "NONE"
                axis_gate_axis_id = payload.get("axis_gate_axis_id")
                out["axis_gate_axis_id"] = (
                    str(axis_gate_axis_id).strip()
                    if isinstance(axis_gate_axis_id, str) and str(axis_gate_axis_id).strip()
                    else None
                )
                out["axis_gate_bundle_present_b"] = bool(payload.get("axis_gate_bundle_present_b", False))
                axis_gate_bundle_sha256 = payload.get("axis_gate_bundle_sha256")
                out["axis_gate_bundle_sha256"] = (
                    str(axis_gate_bundle_sha256).strip()
                    if isinstance(axis_gate_bundle_sha256, str) and str(axis_gate_bundle_sha256).strip()
                    else None
                )
                out["axis_gate_checked_relpaths_v1"] = _canonical_axis_gate_relpaths(
                    payload.get("axis_gate_checked_relpaths_v1")
                )
    if out["axis_gate_reason_code"] == "NONE":
        promo_reason = str(promotion_reason_code or "").strip().upper()
        if promo_reason.startswith("AXIS_GATE_SAFE_HALT:"):
            out["axis_gate_reason_code"] = "SAFE_HALT"
            out["axis_gate_required_b"] = True
        elif promo_reason.startswith("AXIS_GATE_SAFE_SPLIT:"):
            out["axis_gate_reason_code"] = "SAFE_SPLIT"
            out["axis_gate_required_b"] = True
    return out


def _latest_sh1_precheck_payload(state_dir: Path) -> dict[str, Any] | None:
    subruns_dir = state_dir / "subruns"
    if not subruns_dir.exists() or not subruns_dir.is_dir():
        return None
    rows = sorted(
        subruns_dir.glob("*_rsi_ge_symbiotic_optimizer_sh1_v0_1/precheck/sha256_*.candidate_precheck_receipt_v1.json"),
        key=lambda row: row.as_posix(),
    )
    if not rows:
        return None
    payload = load_canon_dict(rows[-1])
    return payload if isinstance(payload, dict) else None


def _latest_sh1_dispatch_payload(state_dir: Path) -> dict[str, Any] | None:
    dispatch_dir = state_dir / "dispatch"
    if not dispatch_dir.exists() or not dispatch_dir.is_dir():
        return None
    rows = sorted(dispatch_dir.glob("*/sha256_*.omega_dispatch_receipt_v1.json"), key=lambda row: row.as_posix())
    if not rows:
        return None
    for path in reversed(rows):
        payload = load_canon_dict(path)
        if not isinstance(payload, dict):
            continue
        if str(payload.get("campaign_id", "")).strip() != "rsi_ge_symbiotic_optimizer_sh1_v0_1":
            continue
        return payload
    return None


def _latest_sh1_utility_payload(state_dir: Path) -> dict[str, Any] | None:
    dispatch_dir = state_dir / "dispatch"
    if not dispatch_dir.exists() or not dispatch_dir.is_dir():
        return None
    utility_candidates: list[Path] = []
    for row in sorted(dispatch_dir.glob("*"), key=lambda item: item.as_posix()):
        if not row.exists() or not row.is_dir():
            continue
        dispatch_payload, _dispatch_hash = _latest_payload(row, "omega_dispatch_receipt_v1.json")
        if not isinstance(dispatch_payload, dict):
            continue
        if str(dispatch_payload.get("campaign_id", "")).strip() != "rsi_ge_symbiotic_optimizer_sh1_v0_1":
            continue
        utility_candidates.extend(
            sorted(
                row.glob("promotion/sha256_*.utility_proof_receipt_v1.json"),
                key=lambda item: item.as_posix(),
            )
        )
    if not utility_candidates:
        return None
    payload = load_canon_dict(utility_candidates[-1])
    return payload if isinstance(payload, dict) else None


def _latest_ccap_receipt_payload(state_dir: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not state_dir.exists() or not state_dir.is_dir():
        return None, None
    rows = sorted(
        [
            *state_dir.glob("dispatch/*/verifier/sha256_*.ccap_receipt_v1.json"),
            *state_dir.glob("dispatch/*/verifier/ccap_receipt_v1.json"),
        ],
        key=lambda row: row.as_posix(),
    )
    if not rows:
        return None, None
    path = rows[-1]
    payload = load_canon_dict(path)
    if not isinstance(payload, dict):
        return None, None
    digest = None
    if path.name.startswith("sha256_") and ".ccap_receipt_v1.json" in path.name:
        digest = "sha256:" + path.name.split(".", 1)[0].split("_", 1)[1]
    else:
        digest = canon_hash_obj(payload)
    return payload, digest


def _ccap_refutation_cert_for_ccap_id(*, state_dir: Path, ccap_id: str) -> tuple[str | None, str | None]:
    if not _is_sha256(ccap_id):
        return None, None
    rows = sorted(
        [
            *state_dir.glob("subruns/*/ccap/refutations/sha256_*.ccap_refutation_cert_v1.json"),
            *state_dir.glob("subruns/*/ccap/refutations/ccap_refutation_cert_v1.json"),
        ],
        key=lambda row: row.as_posix(),
    )
    for path in reversed(rows):
        payload = load_canon_dict(path)
        if not isinstance(payload, dict):
            continue
        if str(payload.get("ccap_id", "")).strip() != ccap_id:
            continue
        code = str(payload.get("refutation_code", "")).strip() or None
        detail = str(payload.get("detail", "")).strip() or None
        return code, detail
    return None, None


def _ccap_refutation_fields(*, ccap_payload: dict[str, Any] | None, state_dir: Path) -> tuple[str | None, str | None]:
    if not isinstance(ccap_payload, dict):
        return None, None
    ref_code = ccap_payload.get("refutation_code")
    ref_summary = ccap_payload.get("refutation_summary")
    if not ref_code and isinstance(ccap_payload.get("refutation"), dict):
        ref_code = ccap_payload["refutation"].get("code")
        ref_summary = ccap_payload["refutation"].get("summary")
    code = str(ref_code).strip() if ref_code is not None else ""
    summary = str(ref_summary).strip() if ref_summary is not None else ""
    if not code:
        cert_code, cert_detail = _ccap_refutation_cert_for_ccap_id(
            state_dir=state_dir,
            ccap_id=str(ccap_payload.get("ccap_id", "")).strip(),
        )
        if cert_code:
            code = cert_code
        if (not summary) and cert_detail:
            summary = cert_detail
    return (code or None), (summary or None)


def _latest_state_verifier_failure_detail_hash(state_dir: Path) -> str | None:
    verifier_dir = state_dir.parent / "state_verifier"
    if not verifier_dir.exists() or not verifier_dir.is_dir():
        return None
    rows = sorted(verifier_dir.glob("sha256_*.state_verifier_failure_detail_v1.json"), key=lambda row: row.as_posix())
    if not rows:
        return None
    path = rows[-1]
    if not path.name.startswith("sha256_"):
        return None
    return "sha256:" + path.name.split(".", 1)[0].split("_", 1)[1]


def _build_subprocess_env(
    *,
    force_lane: str | None,
    force_eval: bool,
    launch_manifest_hash: str | None = None,
) -> dict[str, str]:
    env: dict[str, str] = {}
    for key in ("PATH", "HOME", "LANG", "LC_ALL"):
        value = os.environ.get(key)
        if value:
            env[key] = value
    for key in ENV_ALLOWLIST:
        value = os.environ.get(key)
        if value is not None:
            env[key] = value
    env.setdefault("PYTHONPATH", ".:CDEL-v2:Extension-1/agi-orchestrator")
    env.setdefault("OMEGA_NET_LIVE_OK", "0")
    env.setdefault("OMEGA_META_CORE_ACTIVATION_MODE", "simulate")
    env.setdefault("OMEGA_ALLOW_SIMULATE_ACTIVATION", "1")
    env.setdefault("OMEGA_CCAP_ALLOW_DIRTY_TREE", "1")
    env.setdefault("OMEGA_RETENTION_PRUNE_CCAP_EK_RUNS_B", "1")
    if force_lane:
        env["OMEGA_LONG_RUN_FORCE_LANE"] = force_lane
    else:
        env.pop("OMEGA_LONG_RUN_FORCE_LANE", None)
    if force_eval:
        env["OMEGA_LONG_RUN_FORCE_EVAL"] = "1"
    else:
        env.pop("OMEGA_LONG_RUN_FORCE_EVAL", None)
    if isinstance(launch_manifest_hash, str) and launch_manifest_hash:
        env["OMEGA_LONG_RUN_LAUNCH_MANIFEST_HASH"] = launch_manifest_hash
    return env


def _env_receipt(*, env: dict[str, str]) -> dict[str, Any]:
    selected = {key: env[key] for key in sorted(env.keys()) if key in ENV_ALLOWLIST or key in {"PYTHONPATH"}}
    payload = {
        "schema_name": "run_env_receipt_v1",
        "schema_version": "v1",
        "created_unix_s": int(time.time()),
        "env": selected,
    }
    payload["receipt_id"] = canon_hash_obj({k: v for k, v in payload.items() if k != "receipt_id"})
    return payload


def _repo_relpath(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _write_hashed_payload(
    *,
    dir_path: Path,
    suffix: str,
    payload: dict[str, Any],
    id_field: str | None = None,
) -> tuple[Path, dict[str, Any], str]:
    obj = dict(payload)
    if id_field is not None:
        no_id = dict(obj)
        no_id.pop(id_field, None)
        obj[id_field] = canon_hash_obj(no_id)
    digest = canon_hash_obj(obj)
    dir_path.mkdir(parents=True, exist_ok=True)
    out_path = dir_path / f"sha256_{digest.split(':', 1)[1]}.{suffix}"
    content = canon_bytes(obj) + b"\n"
    if out_path.exists():
        if out_path.read_bytes().rstrip(b"\n") != content.rstrip(b"\n"):
            raise RuntimeError("NONDETERMINISTIC")
        return out_path, obj, digest
    out_path.write_bytes(content)
    return out_path, obj, digest


def _load_or_create_launch_manifest(
    *,
    campaign_pack: Path,
    run_root: Path,
    env_receipt: dict[str, Any],
    start_tick_u64: int,
    max_ticks: int,
    max_disk_bytes: int,
    retain_last_u64: int,
    anchor_every_u64: int,
    canary_every_u64: int,
    force_lane: str | None,
    force_eval: bool,
) -> tuple[Path, dict[str, Any], str]:
    manifest_path = run_root / "configs" / LAUNCH_MANIFEST_NAME
    hashed_dir = run_root / "launch"
    if manifest_path.exists() and manifest_path.is_file():
        payload = load_canon_dict(manifest_path)
        validate_schema_v19(payload, "long_run_launch_manifest_v1")
        expected_manifest_relpath = _repo_relpath(manifest_path)
        if str(payload.get("manifest_relpath", "")).strip() != expected_manifest_relpath:
            raise RuntimeError("NONDETERMINISTIC")
        no_id = dict(payload)
        no_id.pop("manifest_id", None)
        observed = canon_hash_obj(no_id)
        declared = str(payload.get("manifest_id", "")).strip()
        if observed != declared:
            raise RuntimeError("NONDETERMINISTIC")
        _write_hashed_payload(
            dir_path=hashed_dir,
            suffix="long_run_launch_manifest_v1.json",
            payload=payload,
        )
        return manifest_path, payload, declared

    pack_payload = load_canon_dict(campaign_pack)
    pack_hash = canon_hash_obj(pack_payload)
    profile_hash_raw = str(pack_payload.get("long_run_profile_id", "")).strip()
    profile_hash = profile_hash_raw if profile_hash_raw.startswith("sha256:") and len(profile_hash_raw) == 71 else None
    manifest_relpath = _repo_relpath(manifest_path)
    payload: dict[str, Any] = {
        "schema_name": "long_run_launch_manifest_v1",
        "schema_version": "v19_0",
        "manifest_id": "sha256:" + ("0" * 64),
        "created_unix_s": int(time.time()),
        "manifest_relpath": manifest_relpath,
        "run_root_relpath": _repo_relpath(run_root),
        "campaign_pack_relpath": _repo_relpath(campaign_pack),
        "campaign_pack_hash": pack_hash,
        "long_run_profile_hash": profile_hash,
        "env_receipt_hash": canon_hash_obj(env_receipt),
        "execution": {
            "start_tick_u64": int(start_tick_u64),
            "max_ticks": int(max_ticks),
            "max_disk_bytes": int(max_disk_bytes),
            "retain_last_u64": int(retain_last_u64),
            "anchor_every_u64": int(anchor_every_u64),
            "canary_every_u64": int(canary_every_u64),
            "force_lane": str(force_lane).upper() if force_lane else None,
            "force_eval_b": bool(force_eval),
        },
        "env": dict(env_receipt.get("env", {})),
    }
    no_id = dict(payload)
    no_id.pop("manifest_id", None)
    payload["manifest_id"] = canon_hash_obj(no_id)
    validate_schema_v19(payload, "long_run_launch_manifest_v1")
    _write_json(manifest_path, payload)
    _write_hashed_payload(
        dir_path=hashed_dir,
        suffix="long_run_launch_manifest_v1.json",
        payload=payload,
    )
    return manifest_path, payload, str(payload["manifest_id"])


def _append_ledger_event(
    *,
    state_dir: Path,
    tick_u64: int,
    event_type: str,
    artifact_hash: str,
) -> dict[str, Any]:
    ledger_path = state_dir / "ledger" / "omega_ledger_v1.jsonl"
    if not ledger_path.exists() or not ledger_path.is_file():
        raise RuntimeError("MISSING_LEDGER")
    rows = load_ledger(ledger_path)
    prev_event_id = str(rows[-1]["event_id"]) if rows else None
    return append_event(
        ledger_path,
        tick_u64=int(tick_u64),
        event_type=str(event_type),
        artifact_hash=str(artifact_hash),
        prev_event_id=prev_event_id,
    )


def _bind_launch_manifest_to_tick_ledger(
    *,
    state_dir: Path,
    tick_u64: int,
    manifest_relpath: str,
    manifest_hash: str,
) -> tuple[str, str]:
    binding_payload = {
        "schema_name": "long_run_launch_manifest_binding_v1",
        "schema_version": "v1",
        "manifest_relpath": str(manifest_relpath),
        "manifest_hash": str(manifest_hash),
        "bound_tick_u64": int(tick_u64),
    }
    _binding_path, _binding_obj, binding_hash = _write_hashed_payload(
        dir_path=state_dir / "long_run" / "launch",
        suffix="long_run_launch_manifest_binding_v1.json",
        payload=binding_payload,
    )
    ledger_rows = load_ledger(state_dir / "ledger" / "omega_ledger_v1.jsonl")
    existing = [row for row in ledger_rows if str(row.get("event_type", "")) == "LONG_RUN_LAUNCH_MANIFEST"]
    if existing:
        event_artifact_hash = str(existing[-1].get("artifact_hash", "")).strip()
        if event_artifact_hash != binding_hash:
            raise RuntimeError("NONDETERMINISTIC")
        return event_artifact_hash, str(existing[-1].get("event_id", ""))
    event_row = _append_ledger_event(
        state_dir=state_dir,
        tick_u64=int(tick_u64),
        event_type="LONG_RUN_LAUNCH_MANIFEST",
        artifact_hash=binding_hash,
    )
    return binding_hash, str(event_row.get("event_id", ""))


def _state_verifier_outcome(state_dir: Path) -> tuple[bool, str | None, str | None]:
    cmd = [
        sys.executable,
        "-m",
        "cdel.v19_0.verify_rsi_omega_daemon_v1",
        "--mode",
        "full",
        "--state_dir",
        str(state_dir),
    ]
    env = {
        "PYTHONPATH": ".:CDEL-v2:Extension-1/agi-orchestrator",
        "OMEGA_NET_LIVE_OK": "0",
    }
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    failure_detail_hash = _latest_state_verifier_failure_detail_hash(state_dir)
    if proc.returncode == 0 and "VALID" in (proc.stdout or ""):
        return True, None, None
    reason = None
    for line in ((proc.stdout or "") + "\n" + (proc.stderr or "")).splitlines():
        line = line.strip()
        if line.startswith("INVALID:"):
            reason = line.split(":", 1)[1].strip() or "STATE_VERIFIER_INVALID"
            break
    if reason is None:
        reason = "STATE_VERIFIER_FAILED"
    if not str(reason).strip().upper().startswith("NONDETERMINISTIC"):
        failure_detail_hash = None
    return False, reason, failure_detail_hash


def _write_stop_receipt(
    *,
    run_root: Path,
    halt_reason_code: str,
    halt_tick_u64: int,
    last_valid_state_dir_relpath: str,
    manifest_hash: str,
    manifest_relpath: str,
    state_verifier_reason_code: str | None,
    detail: dict[str, Any],
) -> tuple[Path, dict[str, Any], str]:
    payload: dict[str, Any] = {
        "schema_name": "long_run_stop_receipt_v1",
        "schema_version": "v19_0",
        "stop_receipt_id": "sha256:" + ("0" * 64),
        "created_unix_s": int(time.time()),
        "halt_reason_code": str(halt_reason_code),
        "halt_tick_u64": int(max(0, int(halt_tick_u64))),
        "last_valid_state_dir_relpath": str(last_valid_state_dir_relpath),
        "manifest_hash": str(manifest_hash),
        "manifest_relpath": str(manifest_relpath),
        "state_verifier_reason_code": state_verifier_reason_code,
        "detail": dict(detail),
    }
    no_id = dict(payload)
    no_id.pop("stop_receipt_id", None)
    payload["stop_receipt_id"] = canon_hash_obj(no_id)
    validate_schema_v19(payload, "long_run_stop_receipt_v1")
    out_path, out_obj, out_hash = _write_hashed_payload(
        dir_path=run_root / "stop",
        suffix="long_run_stop_receipt_v1.json",
        payload=payload,
    )
    _write_json(run_root / STOP_RECEIPT_NAME, out_obj)
    return out_path, out_obj, out_hash


def _authority_pins_hash() -> str:
    payload = load_canon_dict(REPO_ROOT / "authority" / "authority_pins_v1.json")
    return canon_hash_obj(payload)


def _reason_hist(rows: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        reason = str(row.get("promotion_reason_code", "")).strip() or "none"
        key = reason.lower()
        out[key] = int(out.get(key, 0)) + 1
    return {key: out[key] for key in sorted(out.keys())}


def _write_canary_summary(
    *,
    run_root: Path,
    tick_row: dict[str, Any],
    live_rows: list[dict[str, Any]],
    pins_hash_initial: str,
    canary_every: int,
) -> None:
    tick_u64 = int(tick_row["tick_u64"])
    if tick_u64 <= 0 or (tick_u64 % int(canary_every)) != 0:
        return
    state_dir = Path(str(tick_row["state_dir"]))
    verify_cmd = [
        sys.executable,
        "-m",
        "cdel.v19_0.verify_rsi_omega_daemon_v1",
        "--mode",
        "full",
        "--state_dir",
        str(state_dir),
    ]
    env = dict(os.environ)
    env["PYTHONPATH"] = ".:CDEL-v2:Extension-1/agi-orchestrator"
    verify = subprocess.run(
        verify_cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    replay_valid_b = verify.returncode == 0 and "VALID" in (verify.stdout or "")
    pins_hash_now = _authority_pins_hash()
    pins_drift_b = pins_hash_now != pins_hash_initial
    tail = [row for row in live_rows if int(row.get("tick_u64", -1)) <= tick_u64]
    tail = tail[-DEFAULT_HIST_WINDOW :]
    prev_tail = tail[:-1]
    hist_now = _reason_hist(tail)
    hist_prev = _reason_hist(prev_tail)
    histogram_stable_b = hist_now == hist_prev if prev_tail else True
    payload = {
        "schema_name": "long_run_canary_summary_v1",
        "schema_version": "v1",
        "summary_id": "sha256:" + ("0" * 64),
        "tick_u64": int(tick_u64),
        "state_dir": str(state_dir),
        "replay_valid_b": bool(replay_valid_b),
        "pins_hash_initial": pins_hash_initial,
        "pins_hash_now": pins_hash_now,
        "pins_drift_b": bool(pins_drift_b),
        "reason_hist_window_u64": int(len(tail)),
        "reason_histogram_now": hist_now,
        "reason_histogram_prev": hist_prev,
        "histogram_stable_b": bool(histogram_stable_b),
    }
    payload["summary_id"] = canon_hash_obj({k: v for k, v in payload.items() if k != "summary_id"})
    out_dir = run_root / "canary"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"sha256_{payload['summary_id'].split(':',1)[1]}.long_run_canary_summary_v1.json"
    _write_json(out_path, payload)


def _read_indexes(index_dir: Path) -> tuple[list[dict[str, Any]], set[int]]:
    tick_rows = _load_jsonl(index_dir / TICK_INDEX_NAME)
    prune_rows = _load_jsonl(index_dir / PRUNE_INDEX_NAME)
    pruned_ticks = {int(row.get("tick_u64", -1)) for row in prune_rows if isinstance(row, dict)}
    return tick_rows, pruned_ticks


def _live_rows(tick_rows: list[dict[str, Any]], pruned_ticks: set[int]) -> list[dict[str, Any]]:
    rows = [row for row in tick_rows if int(row.get("tick_u64", -1)) >= 0 and int(row.get("tick_u64", -1)) not in pruned_ticks]
    rows.sort(key=lambda row: int(row.get("tick_u64", -1)))
    return rows


def _compute_live_disk_bytes(rows: list[dict[str, Any]]) -> int:
    total = 0
    for row in rows:
        total += int(max(0, int(row.get("disk_bytes_u64", 0))))
    return int(total)


def _read_head(head_path: Path) -> dict[str, Any] | None:
    if not head_path.exists() or not head_path.is_file():
        return None
    payload = json.loads(head_path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _write_head(head_path: Path, row: dict[str, Any]) -> None:
    payload = {
        "schema_name": "long_run_head_v1",
        "schema_version": "v1",
        "tick_u64": int(row["tick_u64"]),
        "state_dir": str(row["state_dir"]),
        "out_dir": str(row["out_dir"]),
        "snapshot_hash": row.get("snapshot_hash"),
    }
    payload["head_id"] = canon_hash_obj({k: v for k, v in payload.items() if k != "head_id"})
    _write_json(head_path, payload)


def _read_launch_binding_marker(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    payload = load_canon_dict(path)
    if not isinstance(payload, dict):
        return None
    return payload


def _write_launch_binding_marker(
    *,
    path: Path,
    tick_u64: int,
    state_dir: Path,
    binding_hash: str,
    manifest_hash: str,
    manifest_relpath: str,
) -> None:
    payload = {
        "schema_name": "long_run_launch_manifest_binding_marker_v1",
        "schema_version": "v1",
        "marker_id": "sha256:" + ("0" * 64),
        "tick_u64": int(tick_u64),
        "state_dir_relpath": _repo_relpath(state_dir),
        "binding_hash": str(binding_hash),
        "manifest_hash": str(manifest_hash),
        "manifest_relpath": str(manifest_relpath),
    }
    no_id = dict(payload)
    no_id.pop("marker_id", None)
    payload["marker_id"] = canon_hash_obj(no_id)
    _write_json(path, payload)


def _load_health_gate_thresholds(campaign_pack: Path) -> dict[str, int]:
    out = {
        "max_budget_exhaust_u64": 0,
        "max_route_disabled_u64": 0,
    }
    pack_payload = load_canon_dict(campaign_pack)
    profile_rel = str(pack_payload.get("long_run_profile_rel", "")).strip()
    if not profile_rel:
        return out
    profile_path = campaign_pack.parent / profile_rel
    if not profile_path.exists() or not profile_path.is_file():
        return out
    profile_payload = load_canon_dict(profile_path)
    gate = profile_payload.get("frontier_health_gate")
    if not isinstance(gate, dict):
        return out
    out["max_budget_exhaust_u64"] = int(max(0, int(gate.get("max_budget_exhaust_u64", 0))))
    out["max_route_disabled_u64"] = int(max(0, int(gate.get("max_route_disabled_u64", 0))))
    return out


def _retention_keep_ticks(*, live_rows: list[dict[str, Any]], retain_last_u64: int, anchor_every_u64: int) -> set[int]:
    keep: set[int] = set()
    if not live_rows:
        return keep
    tail_rows = live_rows[-max(1, int(retain_last_u64)) :]
    for row in tail_rows:
        keep.add(int(row["tick_u64"]))
    for row in live_rows:
        tick = int(row["tick_u64"])
        if int(anchor_every_u64) > 0 and tick % int(anchor_every_u64) == 0:
            keep.add(tick)
    keep.add(int(live_rows[-1]["tick_u64"]))
    return keep


def _prune_if_needed(
    *,
    run_root: Path,
    max_disk_bytes: int,
    retain_last_u64: int,
    anchor_every_u64: int,
) -> None:
    index_dir = run_root / "index"
    tick_rows, pruned_ticks = _read_indexes(index_dir)
    live_rows = _live_rows(tick_rows, pruned_ticks)
    current_bytes = _compute_live_disk_bytes(live_rows)
    if current_bytes <= int(max_disk_bytes):
        return
    keep_ticks = _retention_keep_ticks(
        live_rows=live_rows,
        retain_last_u64=retain_last_u64,
        anchor_every_u64=anchor_every_u64,
    )
    for row in live_rows:
        tick = int(row["tick_u64"])
        if current_bytes <= int(max_disk_bytes):
            break
        if tick in keep_ticks:
            continue
        out_dir = Path(str(row.get("out_dir", "")))
        if out_dir.exists() and out_dir.is_dir():
            shutil.rmtree(out_dir)
        pruned_ticks.add(tick)
        current_bytes -= int(max(0, int(row.get("disk_bytes_u64", 0))))
        _append_jsonl(
            index_dir / PRUNE_INDEX_NAME,
            {
                "schema_name": "long_run_prune_event_v1",
                "schema_version": "v1",
                "tick_u64": int(tick),
                "out_dir": str(out_dir),
                "reason_code": "DISK_CAP",
            },
        )


def _tick_u64_from_dir_name(name: str) -> int | None:
    text = str(name).strip()
    if not text.startswith("tick_"):
        return None
    token = text.split("_", 1)[1]
    try:
        return int(token)
    except Exception:
        return None


def _cleanup_orphan_ek_runs_startup(*, run_root: Path, tick_rows: list[dict[str, Any]]) -> None:
    indexed_ticks = {int(row.get("tick_u64", -1)) for row in tick_rows if isinstance(row, dict)}
    cleanup_events: list[dict[str, Any]] = []
    for tick_dir in sorted(run_root.glob("tick_*"), key=lambda row: row.as_posix()):
        if not tick_dir.exists() or not tick_dir.is_dir():
            continue
        tick_u64 = _tick_u64_from_dir_name(tick_dir.name)
        if tick_u64 is None:
            continue
        has_index_row_b = int(tick_u64) in indexed_ticks
        lock_paths = sorted(tick_dir.glob("**/LOCK"), key=lambda row: row.as_posix())
        lock_present_b = bool(lock_paths)
        if has_index_row_b and not lock_present_b:
            continue
        ek_run_dirs = sorted(
            [row for row in tick_dir.glob("**/ccap/ek_runs") if row.exists() and row.is_dir()],
            key=lambda row: row.as_posix(),
        )
        if not ek_run_dirs:
            continue
        deleted_relpaths: list[str] = []
        deleted_bytes_u64 = 0
        for ek_runs_dir in ek_run_dirs:
            deleted_bytes_u64 += int(_dir_size_bytes(ek_runs_dir))
            deleted_relpaths.append(ek_runs_dir.relative_to(tick_dir).as_posix())
            shutil.rmtree(ek_runs_dir)
        reason_codes: list[str] = []
        if lock_present_b:
            reason_codes.append("LOCK_PRESENT")
        if not has_index_row_b:
            reason_codes.append("MISSING_INDEX_ROW")
        note_payload = {
            "schema_name": "CLEANUP_ORPHAN_EK_RUNS_V1",
            "schema_version": "v1",
            "tick_u64": int(tick_u64),
            "has_index_row_b": bool(has_index_row_b),
            "lock_present_b": bool(lock_present_b),
            "reason_codes": reason_codes,
            "deleted_ek_runs_relpaths": deleted_relpaths,
            "deleted_bytes_u64": int(deleted_bytes_u64),
        }
        _write_json(tick_dir / ORPHAN_EK_RUNS_NOTE_NAME, note_payload)
        cleanup_events.append(
            {
                **note_payload,
                "tick_dir": str(tick_dir),
            }
        )
    if not cleanup_events:
        return
    index_dir = run_root / "index"
    for row in cleanup_events:
        _append_jsonl(index_dir / ORPHAN_EK_RUNS_LOG_NAME, row)


def run_tick(
    *,
    campaign_pack: Path,
    run_root: Path,
    tick_u64: int,
    prev_state_dir: Path | None,
    force_lane: str | None,
    force_eval: bool,
    launch_manifest_hash: str | None,
) -> dict[str, Any]:
    out_dir = run_root / f"tick_{int(tick_u64):06d}"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    cmd = [
        sys.executable,
        "-m",
        "orchestrator.rsi_omega_daemon_v19_0",
        "--campaign_pack",
        str(campaign_pack),
        "--out_dir",
        str(out_dir),
        "--mode",
        "once",
        "--tick_u64",
        str(int(tick_u64)),
    ]
    if prev_state_dir is not None:
        cmd.extend(["--prev_state_dir", str(prev_state_dir)])
    env = _build_subprocess_env(
        force_lane=force_lane,
        force_eval=force_eval,
        launch_manifest_hash=launch_manifest_hash,
    )
    started = int(time.time())
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    state_dir = out_dir / "daemon" / "rsi_omega_daemon_v19_0" / "state"
    snapshot_payload, snapshot_hash = _latest_payload(state_dir / "snapshot", "omega_tick_snapshot_v1.json")
    tick_outcome_payload, _tick_outcome_hash = _latest_payload(state_dir / "perf", "omega_tick_outcome_v1.json")
    observation_payload, _observation_hash = _latest_payload(state_dir / "observations", "omega_observation_report_v1.json")
    eval_report_payload, _eval_report_hash = _latest_payload(state_dir / "long_run" / "eval", "eval_report_v1.json")
    debt_payload, _debt_hash = _latest_payload(state_dir / "long_run" / "debt", "dependency_debt_state_v1.json")
    routing_payload, _routing_hash = _latest_payload(state_dir / "long_run" / "debt", "dependency_routing_receipt_v1.json")
    routing_reason_codes: list[str] = []
    selected_capability_id = None
    if isinstance(routing_payload, dict):
        raw_reason_codes = routing_payload.get("reason_codes")
        if isinstance(raw_reason_codes, list):
            routing_reason_codes = [str(item).strip() for item in raw_reason_codes if str(item).strip()]
        selected_capability_id = routing_payload.get("selected_capability_id")
    frontier_dispatch_failed_from_routing_b = FRONTIER_DISPATCH_PRE_EVIDENCE_REASON_CODE in set(routing_reason_codes)
    precheck_payload = _latest_sh1_precheck_payload(state_dir)
    sh1_dispatch_payload = _latest_sh1_dispatch_payload(state_dir)
    utility_payload = _latest_sh1_utility_payload(state_dir)
    precheck_forced_heavy_b = bool((precheck_payload or {}).get("forced_heavy_b"))
    sh1_dispatch_overrides = (
        (sh1_dispatch_payload or {}).get("invocation", {}).get("env_overrides")
        if isinstance((sh1_dispatch_payload or {}).get("invocation"), dict)
        else {}
    )
    sh1_dispatch_forced_heavy_b = (
        isinstance(sh1_dispatch_overrides, dict)
        and str(sh1_dispatch_overrides.get("OMEGA_SH1_FORCED_HEAVY_B", "")).strip() == "1"
    )
    sh1_dispatch_wiring_locus_relpath = (
        str(sh1_dispatch_overrides.get("OMEGA_SH1_WIRING_LOCUS_RELPATH", "")).strip()
        if isinstance(sh1_dispatch_overrides, dict)
        else ""
    )
    forced_heavy_sh1_b = bool(
        (
            bool((routing_payload or {}).get("forced_frontier_attempt_b"))
            or bool(precheck_forced_heavy_b)
            or bool(sh1_dispatch_forced_heavy_b)
        )
        and str(selected_capability_id or "").strip() == "RSI_GE_SH1_OPTIMIZER"
    )
    lane_name = None
    lane_frontier_gate_pass_b = None
    lane_invalid_count_u64 = None
    lane_budget_exhaust_count_u64 = None
    lane_route_disabled_count_u64 = None
    lane_payload, _lane_hash = _lane_receipt_final_payload(state_dir)
    if isinstance(lane_payload, dict):
        lane_name = lane_payload.get("lane_name")
        lane_frontier_gate_pass_b = lane_payload.get("frontier_gate_pass_b")
        lane_health = lane_payload.get("health_window")
        if isinstance(lane_health, dict):
            lane_invalid_count_u64 = lane_health.get("invalid_count_u64")
            lane_budget_exhaust_count_u64 = lane_health.get("budget_exhaust_count_u64")
            lane_route_disabled_count_u64 = lane_health.get("route_disabled_count_u64")
    status_ok_b = bool(proc.returncode == 0 and state_dir.exists() and state_dir.is_dir())
    error_class = None
    if not status_ok_b:
        error_class = "TICK_STATE_MISSING" if not state_dir.exists() or not state_dir.is_dir() else "TICK_PROCESS_ERROR"
    promotion_reason_value = (tick_outcome_payload or {}).get("promotion_reason_code")
    ccap_payload, ccap_receipt_hash = _latest_ccap_receipt_payload(state_dir)
    ccap_refutation_code, ccap_refutation_summary = _ccap_refutation_fields(
        ccap_payload=ccap_payload,
        state_dir=state_dir,
    )
    axis_gate_fields = _axis_gate_index_fields(
        state_dir=state_dir,
        promotion_reason_code=(str(promotion_reason_value) if promotion_reason_value is not None else None),
    )
    observation_metrics = observation_payload.get("metrics") if isinstance(observation_payload, dict) else {}
    hard_task_score_q32 = int(
        _metric_q32(
            observation_metrics if isinstance(observation_metrics, dict) else None,
            "hard_task_score_q32",
            fallback_metric_id="hard_task_suite_score_q32",
        )
    )
    hard_task_delta_q32 = int(
        _metric_q32(
            observation_metrics if isinstance(observation_metrics, dict) else None,
            "hard_task_delta_q32",
        )
    )
    hard_task_prev_score_q32 = int(
        _metric_q32(
            observation_metrics if isinstance(observation_metrics, dict) else None,
            "hard_task_prev_score_q32",
        )
    )
    hard_task_baseline_init_b = bool(
        int(
            _metric_q32(
                observation_metrics if isinstance(observation_metrics, dict) else None,
                "hard_task_baseline_init_u64",
            )
        )
        > 0
    )
    utility_metrics = (utility_payload or {}).get("utility_metrics")
    utility_hard_task_delta_q32 = 0
    utility_j_delta_q32_i64 = 0
    utility_hard_task_baseline_init_b = False
    utility_hard_task_prev_score_q32 = 0
    if isinstance(utility_metrics, dict):
        try:
            utility_hard_task_delta_q32 = int(utility_metrics.get("hard_task_delta_q32", 0))
        except Exception:
            utility_hard_task_delta_q32 = 0
        try:
            utility_j_delta_q32_i64 = int(utility_metrics.get("j_delta_q32_i64", 0))
        except Exception:
            utility_j_delta_q32_i64 = 0
        utility_hard_task_baseline_init_b = bool(utility_metrics.get("hard_task_baseline_init_b", False))
        try:
            utility_hard_task_prev_score_q32 = int(utility_metrics.get("hard_task_prev_score_q32", 0))
        except Exception:
            utility_hard_task_prev_score_q32 = 0
    hard_task_baseline_init_b = bool(hard_task_baseline_init_b or utility_hard_task_baseline_init_b)
    if int(hard_task_prev_score_q32) == 0 and int(utility_hard_task_prev_score_q32) != 0:
        hard_task_prev_score_q32 = int(utility_hard_task_prev_score_q32)
    if hard_task_baseline_init_b:
        hard_task_delta_q32 = 0
    else:
        hard_task_delta_q32 = int(max(hard_task_delta_q32, utility_hard_task_delta_q32))
    j_delta_q32_i64 = 0
    if isinstance(eval_report_payload, dict):
        try:
            j_delta_q32_i64 = int(eval_report_payload.get("delta_j_q32", 0))
        except Exception:
            j_delta_q32_i64 = 0
    if int(j_delta_q32_i64) == 0:
        j_delta_q32_i64 = int(utility_j_delta_q32_i64)
    declared_class_value = str((tick_outcome_payload or {}).get("declared_class", "")).strip().upper()
    promotion_status_value = str((tick_outcome_payload or {}).get("promotion_status", "")).strip().upper()
    ccap_decision_value = str((ccap_payload or {}).get("decision", "")).strip().upper()
    utility_ok_b = bool((utility_payload or {}).get("utility_ok_b", False))
    utility_hard_task_any_gain_b = bool(
        ((utility_payload or {}).get("utility_metrics") or {}).get("hard_task_any_gain_b", False)
    )
    heavy_utility_ok_b = bool(
        declared_class_value in {"FRONTIER_HEAVY", "CANARY_HEAVY"}
        and utility_ok_b
        and utility_hard_task_any_gain_b
    )
    heavy_promoted_b = bool(
        heavy_utility_ok_b
        and promotion_status_value == "PROMOTED"
        and ccap_decision_value in {"PROMOTE", "ACCEPT"}
    )
    row = {
        "schema_name": "long_run_tick_index_row_v1",
        "schema_version": "v1",
        "tick_u64": int(tick_u64),
        "out_dir": str(out_dir),
        "state_dir": str(state_dir),
        "status": "OK" if status_ok_b else "ERROR",
        "exit_code": int(proc.returncode),
        "snapshot_hash": snapshot_hash,
        "lane_name": lane_name,
        "lane_frontier_gate_pass_b": lane_frontier_gate_pass_b,
        "lane_invalid_count_u64": lane_invalid_count_u64,
        "lane_budget_exhaust_count_u64": lane_budget_exhaust_count_u64,
        "lane_route_disabled_count_u64": lane_route_disabled_count_u64,
        "mission_goal_ingest_receipt_hash": (snapshot_payload or {}).get("mission_goal_ingest_receipt_hash"),
        "eval_report_hash": (snapshot_payload or {}).get("eval_report_hash"),
        "subverifier_status": (tick_outcome_payload or {}).get("subverifier_status"),
        "promotion_status": (tick_outcome_payload or {}).get("promotion_status"),
        "promotion_reason_code": promotion_reason_value,
        "candidate_bundle_present_b": (tick_outcome_payload or {}).get("candidate_bundle_present_b"),
        "selected_capability_id": selected_capability_id,
        "declared_class": (tick_outcome_payload or {}).get("declared_class"),
        "effect_class": (tick_outcome_payload or {}).get("effect_class"),
        "action_kind": (tick_outcome_payload or {}).get("action_kind"),
        "hard_lock_active_b": (debt_payload or {}).get("hard_lock_active_b"),
        "frontier_goals_pending_b": (routing_payload or {}).get("frontier_goals_pending_b"),
        "forced_frontier_attempt_b": (routing_payload or {}).get("forced_frontier_attempt_b"),
        "forced_heavy_sh1_b": forced_heavy_sh1_b,
        "sh1_dispatch_forced_heavy_b": bool(sh1_dispatch_forced_heavy_b),
        "sh1_dispatch_wiring_locus_relpath": (sh1_dispatch_wiring_locus_relpath or None),
        "dependency_routing_reason_codes": routing_reason_codes,
        "frontier_dispatch_failed_pre_evidence_b": bool(frontier_dispatch_failed_from_routing_b),
        "frontier_dispatch_pre_evidence_reason_code": (
            FRONTIER_DISPATCH_PRE_EVIDENCE_REASON_CODE if frontier_dispatch_failed_from_routing_b else None
        ),
        "frontier_attempt_counted_b": bool((tick_outcome_payload or {}).get("frontier_attempt_counted_b", False)),
        "axis_gate_required_b": bool(axis_gate_fields["axis_gate_required_b"]),
        "axis_gate_exempted_b": bool(axis_gate_fields["axis_gate_exempted_b"]),
        "axis_gate_reason_code": str(axis_gate_fields["axis_gate_reason_code"]),
        "axis_gate_axis_id": axis_gate_fields["axis_gate_axis_id"],
        "axis_gate_bundle_present_b": bool(axis_gate_fields["axis_gate_bundle_present_b"]),
        "axis_gate_bundle_sha256": axis_gate_fields["axis_gate_bundle_sha256"],
        "axis_gate_checked_relpaths_v1": list(axis_gate_fields["axis_gate_checked_relpaths_v1"]),
        "ccap_receipt_hash": ccap_receipt_hash,
        "ccap_decision": (ccap_payload or {}).get("decision"),
        "ccap_eval_status": (ccap_payload or {}).get("eval_status"),
        "ccap_determinism_check": (ccap_payload or {}).get("determinism_check"),
        "ccap_refutation_code": ccap_refutation_code,
        "ccap_refutation_summary": ccap_refutation_summary,
        "hard_task_score_q32": int(hard_task_score_q32),
        "hard_task_prev_score_q32": int(hard_task_prev_score_q32),
        "hard_task_baseline_init_b": bool(hard_task_baseline_init_b),
        "hard_task_delta_q32": int(hard_task_delta_q32),
        "j_delta_q32_i64": int(j_delta_q32_i64),
        "heavy_utility_ok_b": bool(heavy_utility_ok_b),
        "heavy_promoted_b": bool(heavy_promoted_b),
        "error_class": error_class,
        "disk_bytes_u64": int(_dir_size_bytes(out_dir)) if out_dir.exists() else 0,
        "started_unix_s": int(started),
        "finished_unix_s": int(time.time()),
    }
    if proc.stdout:
        row["stdout_tail"] = proc.stdout.strip().splitlines()[-5:]
    if proc.stderr:
        row["stderr_tail"] = proc.stderr.strip().splitlines()[-5:]
    return row


def run_loop(
    *,
    campaign_pack: Path,
    run_root: Path,
    start_tick_u64: int,
    max_ticks: int,
    max_disk_bytes: int,
    retain_last_u64: int,
    anchor_every_u64: int,
    canary_every_u64: int,
    force_lane: str | None,
    force_eval: bool,
    stop_on_error: bool,
) -> None:
    run_root.mkdir(parents=True, exist_ok=True)
    index_dir = run_root / "index"
    index_dir.mkdir(parents=True, exist_ok=True)
    env_receipt = _env_receipt(
        env=_build_subprocess_env(
            force_lane=force_lane,
            force_eval=force_eval,
            launch_manifest_hash=None,
        )
    )
    _write_json(run_root / ENV_RECEIPT_NAME, env_receipt)
    launch_manifest_path, launch_manifest_payload, launch_manifest_hash = _load_or_create_launch_manifest(
        campaign_pack=campaign_pack,
        run_root=run_root,
        env_receipt=env_receipt,
        start_tick_u64=start_tick_u64,
        max_ticks=max_ticks,
        max_disk_bytes=max_disk_bytes,
        retain_last_u64=retain_last_u64,
        anchor_every_u64=anchor_every_u64,
        canary_every_u64=canary_every_u64,
        force_lane=force_lane,
        force_eval=force_eval,
    )
    print(f"launch_manifest_hash={launch_manifest_hash}")
    pins_hash_initial = _authority_pins_hash()
    health_gate_thresholds = _load_health_gate_thresholds(campaign_pack)
    validate_frontier_b = _env_bool("OMEGA_LONG_VALIDATE_FRONTIER", default=False)
    allow_invalid_state_continue_b = _env_bool("OMEGA_LONG_RUN_DEBUG_ALLOW_INVALID_STATE", default=False)
    validate_window_ticks_u64 = _env_u64("OMEGA_LONG_VALIDATE_WINDOW_TICKS", default=150, minimum=1)
    validate_min_hardlocks_u64 = _env_u64("OMEGA_LONG_VALIDATE_MIN_HARDLOCKS", default=1, minimum=0)
    validate_min_forced_u64 = _env_u64("OMEGA_LONG_VALIDATE_MIN_FORCED", default=1, minimum=0)
    validate_min_counted_u64 = _env_u64("OMEGA_LONG_VALIDATE_MIN_COUNTED", default=1, minimum=0)
    manifest_relpath = str(launch_manifest_payload.get("manifest_relpath", _repo_relpath(launch_manifest_path)))

    tick_rows, pruned_ticks = _read_indexes(index_dir)
    _cleanup_orphan_ek_runs_startup(run_root=run_root, tick_rows=tick_rows)
    live_rows = _live_rows(tick_rows, pruned_ticks)
    head = _read_head(index_dir / HEAD_NAME)
    launch_binding_marker_path = index_dir / LAUNCH_BINDING_MARKER_NAME
    launch_binding_marker = _read_launch_binding_marker(launch_binding_marker_path)
    launch_bound_b = launch_binding_marker is not None
    prev_state_dir: Path | None = None
    last_valid_state_dir: Path | None = None
    tick_u64 = int(start_tick_u64)
    if head is not None:
        head_tick = int(head.get("tick_u64", -1))
        head_state_dir = Path(str(head.get("state_dir", "")))
        if head_tick >= 0 and head_state_dir.exists():
            tick_u64 = head_tick + 1
            prev_state_dir = head_state_dir
            last_valid_state_dir = head_state_dir
    elif live_rows:
        last = live_rows[-1]
        prev_state_dir = Path(str(last["state_dir"]))
        tick_u64 = int(last["tick_u64"]) + 1
        if prev_state_dir.exists():
            last_valid_state_dir = prev_state_dir

    if not launch_bound_b and live_rows:
        first_ok = None
        for row in live_rows:
            if str(row.get("status", "")) != "OK":
                continue
            candidate = Path(str(row.get("state_dir", "")))
            if candidate.exists() and candidate.is_dir():
                first_ok = row
                break
        if first_ok is not None:
            state_dir = Path(str(first_ok.get("state_dir", "")))
            tick_for_bind = int(first_ok.get("tick_u64", 0))
            binding_hash, _event_id = _bind_launch_manifest_to_tick_ledger(
                state_dir=state_dir,
                tick_u64=tick_for_bind,
                manifest_relpath=manifest_relpath,
                manifest_hash=launch_manifest_hash,
            )
            _write_launch_binding_marker(
                path=launch_binding_marker_path,
                tick_u64=tick_for_bind,
                state_dir=state_dir,
                binding_hash=binding_hash,
                manifest_hash=launch_manifest_hash,
                manifest_relpath=manifest_relpath,
            )
            launch_bound_b = True

    ticks_run = 0
    stop_receipt_written_b = False
    last_row: dict[str, Any] | None = None
    while max_ticks <= 0 or ticks_run < max_ticks:
        row = run_tick(
            campaign_pack=campaign_pack,
            run_root=run_root,
            tick_u64=tick_u64,
            prev_state_dir=prev_state_dir,
            force_lane=force_lane,
            force_eval=force_eval,
            launch_manifest_hash=launch_manifest_hash,
        )
        hard_stop_reason_code: str | None = None
        hard_stop_detail: dict[str, Any] = {}
        state_verifier_reason_code: str | None = None

        state_dir = Path(str(row.get("state_dir", "")))
        tick_value = int(row.get("tick_u64", tick_u64))
        if not launch_bound_b and str(row.get("status", "")) == "OK" and state_dir.exists() and state_dir.is_dir():
            binding_hash, _event_id = _bind_launch_manifest_to_tick_ledger(
                state_dir=state_dir,
                tick_u64=tick_value,
                manifest_relpath=manifest_relpath,
                manifest_hash=launch_manifest_hash,
            )
            _write_launch_binding_marker(
                path=launch_binding_marker_path,
                tick_u64=tick_value,
                state_dir=state_dir,
                binding_hash=binding_hash,
                manifest_hash=launch_manifest_hash,
                manifest_relpath=manifest_relpath,
            )
            launch_bound_b = True
            row["launch_manifest_bound_b"] = True
            row["launch_manifest_hash"] = launch_manifest_hash
        else:
            row["launch_manifest_bound_b"] = bool(launch_bound_b)
            row["launch_manifest_hash"] = launch_manifest_hash

        if str(row.get("status", "")) == "OK" and state_dir.exists() and state_dir.is_dir():
            valid_b, state_verifier_reason_code, state_verifier_failure_detail_hash = _state_verifier_outcome(state_dir)
            row["state_verifier_valid_b"] = bool(valid_b)
            row["state_verifier_reason_code"] = state_verifier_reason_code
            row["state_verifier_failure_detail_hash"] = state_verifier_failure_detail_hash
            row["error_class"] = None
            if valid_b:
                prev_state_dir = state_dir
                last_valid_state_dir = state_dir
            else:
                if allow_invalid_state_continue_b:
                    prev_state_dir = state_dir
                else:
                    if state_verifier_reason_code == "PRECHECK_FAIL:UNBOUND_DEBT_KEY":
                        hard_stop_reason_code = "PRECHECK_FAIL:UNBOUND_DEBT_KEY"
                    else:
                        hard_stop_reason_code = "STATE_VERIFIER_INVALID"
                    hard_stop_detail = {
                        "state_verifier_reason_code": state_verifier_reason_code,
                    }
        else:
            row["state_verifier_valid_b"] = False
            error_class = None
            if not state_dir.exists() or not state_dir.is_dir():
                error_class = "TICK_STATE_MISSING"
                if hard_stop_reason_code is None and bool(stop_on_error):
                    hard_stop_reason_code = "TICK_STATE_MISSING"
            else:
                error_class = "TICK_PROCESS_ERROR"
                if hard_stop_reason_code is None and bool(stop_on_error):
                    hard_stop_reason_code = "TICK_PROCESS_ERROR"
            state_verifier_reason_code = str(error_class)
            row["state_verifier_reason_code"] = state_verifier_reason_code
            row["state_verifier_failure_detail_hash"] = None
            row["error_class"] = error_class

        row["frontier_attempt_counted_b"] = bool(row.get("frontier_attempt_counted_b", False))

        subverifier_status = str(row.get("subverifier_status", "")).strip()
        if subverifier_status == "INVALID":
            row["harness_control_reason_code"] = "SUBVERIFIER_INVALID_CONTINUE"
        else:
            row["harness_control_reason_code"] = "CONTINUE"

        _attach_frontier_attempt_quality_telemetry(rows=live_rows, row=row)
        _attach_hard_lock_transition_telemetry(rows=live_rows, row=row)
        _attach_axis_gate_telemetry(rows=live_rows, row=row)
        _attach_heavy_success_telemetry(rows=live_rows, row=row)

        frontier_gate_pass_raw = row.get("lane_frontier_gate_pass_b")
        frontier_gate_pass = frontier_gate_pass_raw if isinstance(frontier_gate_pass_raw, bool) else None
        budget_count = int(max(0, int(row.get("lane_budget_exhaust_count_u64") or 0)))
        route_count = int(max(0, int(row.get("lane_route_disabled_count_u64") or 0)))
        budget_breach = budget_count > int(health_gate_thresholds["max_budget_exhaust_u64"])
        route_breach = route_count > int(health_gate_thresholds["max_route_disabled_u64"])
        if hard_stop_reason_code is None and frontier_gate_pass is False and (budget_breach or route_breach):
            if budget_breach and route_breach:
                hard_stop_reason_code = "HEALTH_GATE_BUDGET_AND_ROUTE"
            elif budget_breach:
                hard_stop_reason_code = "HEALTH_GATE_BUDGET_EXHAUST"
            else:
                hard_stop_reason_code = "HEALTH_GATE_ROUTE_DISABLED"
            hard_stop_detail = {
                "lane_name": row.get("lane_name"),
                "lane_budget_exhaust_count_u64": budget_count,
                "lane_route_disabled_count_u64": route_count,
                "max_budget_exhaust_u64": int(health_gate_thresholds["max_budget_exhaust_u64"]),
                "max_route_disabled_u64": int(health_gate_thresholds["max_route_disabled_u64"]),
            }

        if hard_stop_reason_code is None and str(row.get("status", "")) != "OK" and bool(stop_on_error):
            hard_stop_reason_code = "STOP_ON_ERROR"
            hard_stop_detail = {
                "exit_code": int(row.get("exit_code", 0)),
            }

        if hard_stop_reason_code is None:
            mandatory_reason, mandatory_detail = _mandatory_frontier_guard_reason(
                rows=[*live_rows, row],
                tick_u64=tick_value,
            )
            if mandatory_reason is not None:
                hard_stop_reason_code = mandatory_reason
                hard_stop_detail = mandatory_detail

        if hard_stop_reason_code is None and validate_frontier_b:
            ticks_seen_this_invocation = int(ticks_run + 1)
            if ticks_seen_this_invocation >= int(validate_window_ticks_u64):
                validation_rows = [*live_rows, row]
                summary = _frontier_precheck_summary(
                    rows=validation_rows,
                    window_ticks_u64=int(validate_window_ticks_u64),
                    min_hardlocks_u64=int(validate_min_hardlocks_u64),
                    min_forced_u64=int(validate_min_forced_u64),
                    min_counted_u64=int(validate_min_counted_u64),
                )
                reason, missing = _frontier_precheck_reason(summary)
                if reason is not None:
                    hard_stop_reason_code = reason
                    hard_stop_detail = {
                        "validation_window_ticks_u64": int(validate_window_ticks_u64),
                        **summary,
                        "missing_conditions": [str(item) for item in missing],
                    }

        row["hard_stop_reason_code"] = hard_stop_reason_code
        if hard_stop_reason_code is not None:
            last_valid_state_rel = _repo_relpath(last_valid_state_dir) if isinstance(last_valid_state_dir, Path) else ""
            stop_path, stop_obj, stop_hash = _write_stop_receipt(
                run_root=run_root,
                halt_reason_code=hard_stop_reason_code,
                halt_tick_u64=tick_value,
                last_valid_state_dir_relpath=last_valid_state_rel,
                manifest_hash=launch_manifest_hash,
                manifest_relpath=manifest_relpath,
                state_verifier_reason_code=state_verifier_reason_code,
                detail=hard_stop_detail,
            )
            row["stop_receipt_hash"] = stop_hash
            row["stop_receipt_relpath"] = _repo_relpath(stop_path)
            row["stop_receipt_ledger_bound_b"] = False
            stop_receipt_written_b = True
            if str(row.get("status", "")) == "OK" and state_dir.exists() and state_dir.is_dir():
                try:
                    _state_stop_path, _state_stop_obj, state_stop_hash = _write_hashed_payload(
                        dir_path=state_dir / "long_run" / "stop",
                        suffix="long_run_stop_receipt_v1.json",
                        payload=stop_obj,
                        id_field="stop_receipt_id",
                    )
                    if state_stop_hash != stop_hash:
                        raise RuntimeError("NONDETERMINISTIC")
                    _ = _append_ledger_event(
                        state_dir=state_dir,
                        tick_u64=tick_value,
                        event_type="LONG_RUN_STOP_RECEIPT",
                        artifact_hash=stop_hash,
                    )
                    row["stop_receipt_ledger_bound_b"] = True
                except Exception:
                    row["stop_receipt_ledger_bound_b"] = False

        _append_jsonl(index_dir / TICK_INDEX_NAME, row)
        last_row = row
        tick_rows.append(row)
        if row.get("state_verifier_valid_b") is True:
            _write_head(index_dir / HEAD_NAME, row)
        _prune_if_needed(
            run_root=run_root,
            max_disk_bytes=max_disk_bytes,
            retain_last_u64=retain_last_u64,
            anchor_every_u64=anchor_every_u64,
        )
        tick_rows, pruned_ticks = _read_indexes(index_dir)
        live_rows = _live_rows(tick_rows, pruned_ticks)
        _write_canary_summary(
            run_root=run_root,
            tick_row=row,
            live_rows=live_rows,
            pins_hash_initial=pins_hash_initial,
            canary_every=canary_every_u64,
        )
        if hard_stop_reason_code is not None:
            break
        tick_u64 += 1
        ticks_run += 1

    if (not stop_receipt_written_b) and isinstance(last_row, dict) and max_ticks > 0 and ticks_run >= max_ticks:
        final_tick_u64 = int(max(0, int(last_row.get("tick_u64", 0))))
        final_state_dir = Path(str(last_row.get("state_dir", "")).strip())
        state_verifier_reason_code = (
            str(last_row.get("state_verifier_reason_code", "")).strip() or None
            if isinstance(last_row.get("state_verifier_reason_code"), str)
            else None
        )
        last_valid_state_rel = _repo_relpath(last_valid_state_dir) if isinstance(last_valid_state_dir, Path) else ""
        stop_path, stop_obj, stop_hash = _write_stop_receipt(
            run_root=run_root,
            halt_reason_code="CLEAN_EXIT:MAX_TICKS_REACHED",
            halt_tick_u64=final_tick_u64,
            last_valid_state_dir_relpath=last_valid_state_rel,
            manifest_hash=launch_manifest_hash,
            manifest_relpath=manifest_relpath,
            state_verifier_reason_code=state_verifier_reason_code,
            detail={
                "max_ticks_u64": int(max_ticks),
                "ticks_run_u64": int(ticks_run),
                "final_tick_u64": int(final_tick_u64),
            },
        )
        if final_state_dir.exists() and final_state_dir.is_dir():
            try:
                _state_stop_path, _state_stop_obj, state_stop_hash = _write_hashed_payload(
                    dir_path=final_state_dir / "long_run" / "stop",
                    suffix="long_run_stop_receipt_v1.json",
                    payload=stop_obj,
                    id_field="stop_receipt_id",
                )
                if state_stop_hash != stop_hash:
                    raise RuntimeError("NONDETERMINISTIC")
                _ = _append_ledger_event(
                    state_dir=final_state_dir,
                    tick_u64=final_tick_u64,
                    event_type="LONG_RUN_STOP_RECEIPT",
                    artifact_hash=stop_hash,
                )
            except Exception:
                pass
        _append_jsonl(
            index_dir / "long_run_stop_receipt_index_v1.jsonl",
            {
                "tick_u64": int(final_tick_u64),
                "stop_receipt_hash": str(stop_hash),
                "stop_receipt_relpath": _repo_relpath(stop_path),
                "halt_reason_code": "CLEAN_EXIT:MAX_TICKS_REACHED",
            },
        )


def main() -> None:
    ap = argparse.ArgumentParser(prog="run_long_disciplined_loop_v1")
    ap.add_argument("--campaign_pack", default=DEFAULT_PACK)
    ap.add_argument("--run_root", default=DEFAULT_RUN_ROOT)
    ap.add_argument("--start_tick_u64", type=int, default=1)
    ap.add_argument("--max_ticks", type=int, default=0, help="0 means run forever")
    ap.add_argument("--max_disk_bytes", type=int, default=DEFAULT_MAX_DISK_BYTES)
    ap.add_argument("--retain_last_u64", type=int, default=DEFAULT_RETAIN_LAST)
    ap.add_argument("--anchor_every_u64", type=int, default=DEFAULT_ANCHOR_EVERY)
    ap.add_argument("--canary_every_u64", type=int, default=DEFAULT_CANARY_EVERY)
    ap.add_argument("--force_lane", choices=["BASELINE", "CANARY", "FRONTIER"])
    ap.add_argument("--force_eval", action="store_true")
    ap.add_argument("--stop_on_error", action="store_true")
    args = ap.parse_args()

    run_loop(
        campaign_pack=(REPO_ROOT / args.campaign_pack).resolve(),
        run_root=(REPO_ROOT / args.run_root).resolve(),
        start_tick_u64=int(args.start_tick_u64),
        max_ticks=int(args.max_ticks),
        max_disk_bytes=int(args.max_disk_bytes),
        retain_last_u64=int(args.retain_last_u64),
        anchor_every_u64=int(args.anchor_every_u64),
        canary_every_u64=int(args.canary_every_u64),
        force_lane=args.force_lane,
        force_eval=bool(args.force_eval),
        stop_on_error=bool(args.stop_on_error),
    )


if __name__ == "__main__":
    main()
