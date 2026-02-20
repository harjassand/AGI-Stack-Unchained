#!/usr/bin/env python3
"""Run a deterministic omega v19 benchmark suite and emit summary artifacts."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for entry in [_REPO_ROOT, _REPO_ROOT / "CDEL-v2"]:
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from cdel.v18_0.omega_common_v1 import hash_file_stream, load_jsonl
from cdel.v18_0.omega_promotion_bundle_v1 import extract_touched_paths, load_bundle
from orchestrator.omega_v19_0.coordinator_v1 import run_tick

_SKILL_FAMILIES = {"CODE", "SYSTEM", "KERNEL", "METASEARCH", "VAL", "SCIENCE"}
_Q32_ONE = 1 << 32
_PROMOTION_SKIP_REASON_BUCKETS = (
    "ALREADY_ACTIVE",
    "NO_PROMOTION_BUNDLE",
    "FORBIDDEN_PATH",
    "SUBVERIFIER_INVALID",
    "META_CORE_REJECT",
    "TOOLCHAIN_MISMATCH",
    "UNKNOWN",
)
_META_CORE_REQUIRED_BUNDLE_FILES: tuple[str, ...] = (
    "constitution.manifest.json",
    "ruleset/accept.ir.json",
    "ruleset/costvec.ir.json",
    "ruleset/migrate.ir.json",
    "proofs/dominance_witness.json",
    "proofs/proof_bundle.manifest.json",
)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _write_md(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _is_hex64(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _bundle_complete(meta_core_root: Path, bundle_hex: str) -> bool:
    if not _is_hex64(bundle_hex):
        return False
    bundle_dir = meta_core_root / "store" / "bundles" / bundle_hex
    if not bundle_dir.is_dir():
        return False
    for rel in _META_CORE_REQUIRED_BUNDLE_FILES:
        path = bundle_dir / rel
        if not path.exists() or not path.is_file():
            return False
    return True


def _ensure_meta_core_active_bundle(*, repo_root: Path) -> None:
    meta_core_root = repo_root / "meta-core"
    active_ptr = meta_core_root / "active" / "ACTIVE_BUNDLE"
    prev_ptr = meta_core_root / "active" / "PREV_ACTIVE_BUNDLE"
    store_root = meta_core_root / "store" / "bundles"
    if not store_root.is_dir():
        return

    active_hex = active_ptr.read_text(encoding="utf-8").strip() if active_ptr.exists() else ""
    prev_hex = prev_ptr.read_text(encoding="utf-8").strip() if prev_ptr.exists() else ""

    if _bundle_complete(meta_core_root, active_hex):
        return

    candidates: list[str] = []
    if _bundle_complete(meta_core_root, prev_hex):
        candidates.append(prev_hex)

    for row in sorted(store_root.iterdir(), key=lambda p: p.name):
        if not row.is_dir():
            continue
        hex_name = row.name.strip()
        if hex_name in candidates:
            continue
        if _bundle_complete(meta_core_root, hex_name):
            candidates.append(hex_name)
            break

    if not candidates:
        return

    selected = candidates[0]
    if active_hex != selected:
        active_ptr.write_text(selected + "\n", encoding="utf-8")
    if not prev_hex:
        prev_ptr.write_text(selected + "\n", encoding="utf-8")


def _state_dir(run_dir: Path) -> Path:
    return run_dir / "daemon" / "rsi_omega_daemon_v19_0" / "state"


def _empty_promotion_skip_reason_counts() -> dict[str, int]:
    return {str(key): 0 for key in _PROMOTION_SKIP_REASON_BUCKETS}


def _normalize_promotion_skip_reason_counts(raw: Any) -> dict[str, int]:
    out = _empty_promotion_skip_reason_counts()
    if not isinstance(raw, dict):
        return out
    for key in _PROMOTION_SKIP_REASON_BUCKETS:
        out[key] = max(0, int(raw.get(key, 0)))
    return out


def _prepare_campaign_pack(*, run_dir: Path, make_base_goal_queue_empty: bool) -> Path:
    src = _REPO_ROOT / "campaigns" / "rsi_omega_daemon_v19_0"
    dst = run_dir / "_benchmark_pack"
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst)
    if make_base_goal_queue_empty:
        _write_json(
            dst / "goals" / "omega_goal_queue_v1.json",
            {"schema_version": "omega_goal_queue_v1", "goals": []},
        )
    return dst / "rsi_omega_daemon_pack_v1.json"


def _run_tick_loop(*, campaign_pack: Path, run_dir: Path, ticks: int) -> int:
    _ensure_meta_core_active_bundle(repo_root=_REPO_ROOT)
    prev_state_dir: Path | None = None
    ticks_completed = 0
    for tick_u64 in range(1, int(ticks) + 1):
        result = run_tick(
            campaign_pack=campaign_pack,
            out_dir=run_dir,
            tick_u64=tick_u64,
            prev_state_dir=prev_state_dir,
        )
        ticks_completed = tick_u64
        prev_state_dir = _state_dir(run_dir)
        if bool(result.get("safe_halt", False)):
            break
    return ticks_completed


def _run_tool(tool_path: Path, *, series_prefix: str, runs_root: Path, out_path: Path) -> bool:
    cmd = [
        sys.executable,
        str(tool_path),
        "--series_prefix",
        series_prefix,
        "--runs_root",
        str(runs_root),
        "--out",
        str(out_path),
    ]
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{_REPO_ROOT}:{_REPO_ROOT / 'CDEL-v2'}:{env.get('PYTHONPATH', '')}".rstrip(":")
    run = subprocess.run(cmd, cwd=_REPO_ROOT, check=False, env=env, capture_output=True, text=True)
    return int(run.returncode) == 0


def _capability_family(capability_id: str) -> str | None:
    value = str(capability_id).strip().upper()
    for family in sorted(_SKILL_FAMILIES):
        if value.endswith(f"_{family}") or family in value:
            return family
    return None


def _latest_payload(perf_dir: Path, suffix: str) -> dict[str, Any] | None:
    rows = sorted(perf_dir.glob(f"sha256_*.{suffix}"))
    if not rows:
        return None
    best_payload: dict[str, Any] | None = None
    best_tick = -1
    for path in rows:
        payload = _load_json(path)
        tick_u64 = int(payload.get("tick_u64", -1))
        if tick_u64 >= best_tick:
            best_tick = tick_u64
            best_payload = payload
    return best_payload


def _promotion_summary(*, run_dir: Path, series_prefix: str, runs_root: Path) -> dict[str, Any]:
    state_dir = _state_dir(run_dir)
    promotions = sorted(state_dir.glob("dispatch/*/promotion/sha256_*.omega_promotion_receipt_v1.json"))
    status_counts = {"PROMOTED": 0, "REJECTED": 0, "SKIPPED": 0}
    promotion_skip_reason_counts = _empty_promotion_skip_reason_counts()
    touched_counts: dict[str, int] = {}
    unique_promotions: set[tuple[str, str]] = set()
    unique_promoted_families: set[str] = set()
    for receipt_path in promotions:
        payload = _load_json(receipt_path)
        result = payload.get("result")
        status = ""
        reason_code = ""
        if isinstance(result, dict):
            status = str(result.get("status", ""))
            reason_code_raw = result.get("reason_code")
            if isinstance(reason_code_raw, str):
                reason_code = reason_code_raw.strip()
        if status in status_counts:
            status_counts[status] = int(status_counts[status]) + 1
        if status != "PROMOTED" and reason_code:
            bucket = reason_code if reason_code in promotion_skip_reason_counts else "UNKNOWN"
            promotion_skip_reason_counts[bucket] = int(promotion_skip_reason_counts.get(bucket, 0)) + 1
        if status != "PROMOTED":
            continue

        binding_path = receipt_path.parent / "omega_activation_binding_v1.json"
        if binding_path.exists() and binding_path.is_file():
            binding_payload = _load_json(binding_path)
            capability_id = str(binding_payload.get("capability_id", "")).strip()
            activation_key = str(binding_payload.get("activation_key", "")).strip()
            if capability_id and activation_key:
                unique_promotions.add((capability_id, activation_key))
                family = _capability_family(capability_id)
                if family is not None:
                    unique_promoted_families.add(family)

        bundle_hash = str(payload.get("promotion_bundle_hash", ""))
        if not bundle_hash.startswith("sha256:"):
            continue
        bundle_hex = bundle_hash.split(":", 1)[1]
        bundle_candidates = sorted(state_dir.glob(f"subruns/**/sha256_{bundle_hex}.*.json"))
        if not bundle_candidates:
            continue
        bundle_payload, _ = load_bundle(bundle_candidates[0])
        for path_rel in extract_touched_paths(bundle_payload):
            touched_counts[path_rel] = int(touched_counts.get(path_rel, 0)) + 1

    activation_paths = sorted(state_dir.glob("dispatch/*/activation/sha256_*.omega_activation_receipt_v1.json"))
    activation_success_u64 = 0
    activation_denied_u64 = 0
    activation_pointer_swap_failed_u64 = 0
    activation_binding_mismatch_u64 = 0
    activation_failure_reason_counts: dict[str, int] = {}
    unique_activations_applied: set[tuple[str, str]] = set()
    for path in activation_paths:
        payload = _load_json(path)
        reasons_raw = payload.get("reasons")
        reasons: list[str] = []
        if isinstance(reasons_raw, list):
            reasons = [str(row).strip() for row in reasons_raw if str(row).strip()]
        reasons_set = set(reasons)
        if "META_CORE_DENIED" in reasons_set:
            activation_denied_u64 += 1
        if "POINTER_SWAP_FAILED" in reasons_set:
            activation_pointer_swap_failed_u64 += 1
        if "BINDING_MISSING_OR_MISMATCH" in reasons_set:
            activation_binding_mismatch_u64 += 1

        success = bool(payload.get("activation_success", False))
        if success:
            activation_success_u64 += 1
            binding_path = path.parent.parent / "promotion" / "omega_activation_binding_v1.json"
            if binding_path.exists() and binding_path.is_file():
                binding_payload = _load_json(binding_path)
                capability_id = str(binding_payload.get("capability_id", "")).strip()
                activation_key = str(binding_payload.get("activation_key", "")).strip()
                if capability_id and activation_key:
                    unique_activations_applied.add((capability_id, activation_key))
            continue

        for reason in reasons:
            activation_failure_reason_counts[reason] = int(activation_failure_reason_counts.get(reason, 0)) + 1

    top_touched_paths = sorted(
        [{"path": key, "count_u64": int(value)} for key, value in touched_counts.items()],
        key=lambda row: (-int(row["count_u64"]), str(row["path"])),
    )[:20]
    top_activation_failure_reasons = sorted(
        [{"reason": key, "count_u64": int(value)} for key, value in activation_failure_reason_counts.items()],
        key=lambda row: (-int(row["count_u64"]), str(row["reason"])),
    )[:20]

    return {
        "schema_version": "OMEGA_PROMOTION_SUMMARY_v1",
        "series_prefix": series_prefix,
        "runs_root": runs_root.as_posix(),
        "promoted_u64": int(status_counts["PROMOTED"]),
        "rejected_u64": int(status_counts["REJECTED"]),
        "skipped_u64": int(status_counts["SKIPPED"]),
        "activation_success_u64": int(activation_success_u64),
        "activation_denied_u64": int(activation_denied_u64),
        "activation_pointer_swap_failed_u64": int(activation_pointer_swap_failed_u64),
        "activation_binding_mismatch_u64": int(activation_binding_mismatch_u64),
        "unique_promotions_u64": int(len(unique_promotions)),
        "unique_activations_applied_u64": int(len(unique_activations_applied)),
        "unique_promoted_families_u64": int(len(unique_promoted_families)),
        "unique_promoted_families": sorted(unique_promoted_families),
        "promotion_skip_reason_counts": promotion_skip_reason_counts,
        "activation_failure_reason_counts": top_activation_failure_reasons,
        "top_touched_paths": top_touched_paths,
    }


def _state_rows(state_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted((state_dir / "state").glob("sha256_*.omega_state_v1.json")):
        payload = _load_json(path)
        tick_u64 = int(payload.get("tick_u64", -1))
        if tick_u64 < 0:
            continue
        rows.append(payload)
    rows.sort(key=lambda row: int(row.get("tick_u64", 0)))
    return rows


def _observation_rows(state_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    obs_dir = state_dir / "observations"
    for path in sorted(obs_dir.glob("sha256_*.omega_observation_report_v1.json"), key=lambda row: row.as_posix()):
        payload = _load_json(path)
        tick_u64 = int(payload.get("tick_u64", -1))
        if tick_u64 < 0:
            continue
        rows.append(payload)
    rows.sort(key=lambda row: int(row.get("tick_u64", 0)))
    return rows


def _scout_dispatch_void_hash_history(state_dir: Path) -> dict[str, Any]:
    dispatch_paths = sorted(
        state_dir.glob("dispatch/*/sha256_*.omega_dispatch_receipt_v1.json"),
        key=lambda row: row.as_posix(),
    )
    scout_rows: list[tuple[int, str, Path]] = []
    scout_dispatch_u64 = 0
    last_scout_tick_u64 = 0
    for path in dispatch_paths:
        payload = _load_json(path)
        if str(payload.get("campaign_id", "")) != "rsi_polymath_scout_v1":
            continue
        if int(payload.get("return_code", 1)) != 0:
            continue
        scout_dispatch_u64 += 1
        tick_u64 = max(0, int(payload.get("tick_u64", 0)))
        last_scout_tick_u64 = max(last_scout_tick_u64, tick_u64)
        subrun_obj = payload.get("subrun")
        if not isinstance(subrun_obj, dict):
            continue
        subrun_root_rel = str(subrun_obj.get("subrun_root_rel", "")).strip()
        if not subrun_root_rel:
            continue
        void_path = state_dir / subrun_root_rel / "polymath" / "registry" / "polymath_void_report_v1.jsonl"
        scout_rows.append((int(tick_u64), path.as_posix(), void_path))

    void_hash_history: list[str] = []
    for _tick_u64, _dispatch_path, void_path in sorted(scout_rows, key=lambda row: (int(row[0]), str(row[1]))):
        if not void_path.exists() or not void_path.is_file():
            continue
        rows = load_jsonl(void_path)
        if not rows:
            continue
        void_hash_history.append(hash_file_stream(void_path))
    return {
        "scout_dispatch_u64": int(scout_dispatch_u64),
        "last_scout_tick_u64": int(last_scout_tick_u64),
        "void_hash_history": list(void_hash_history),
        "scout_dispatch_receipt_paths": sorted(set(str(row[1]) for row in scout_rows)),
        "scout_void_report_paths": sorted(set(path.as_posix() for _, _, path in scout_rows)),
    }


def _observation_void_hash_history(observation_rows: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for row in observation_rows:
        sources = row.get("sources")
        if not isinstance(sources, list):
            continue
        for source in sources:
            if not isinstance(source, dict):
                continue
            if str(source.get("schema_id", "")) != "polymath_void_report_v1":
                continue
            artifact_hash = str(source.get("artifact_hash", "")).strip()
            if artifact_hash.startswith("sha256:"):
                out.append(artifact_hash)
                break
    return out


def _polymath_gate_stats(run_dir: Path) -> dict[str, Any]:
    state_dir = _state_dir(run_dir)
    observation_rows = _observation_rows(state_dir)
    scout_hash_stats = _scout_dispatch_void_hash_history(state_dir)
    scout_dispatch_u64 = int(scout_hash_stats.get("scout_dispatch_u64", 0))
    scout_void_hash_history = list(scout_hash_stats.get("void_hash_history", []))
    observation_void_hash_history = _observation_void_hash_history(observation_rows)
    if len(scout_void_hash_history) >= 2:
        void_hash_history = list(scout_void_hash_history)
    else:
        # With a single scout dispatch, fold observation-linked void hashes so
        # short runs can still prove deterministic movement in the same lane.
        void_hash_history = list(scout_void_hash_history)
        for digest in observation_void_hash_history:
            value = str(digest).strip()
            if not value.startswith("sha256:"):
                continue
            if not void_hash_history or value != str(void_hash_history[-1]):
                void_hash_history.append(value)
    if not void_hash_history:
        void_hash_history = list(observation_void_hash_history)
    domains_bootstrapped_series: list[int] = []
    portfolio_score_series: list[int] = []
    for row in observation_rows:
        metrics = row.get("metrics")
        if isinstance(metrics, dict):
            domains_bootstrapped_series.append(max(0, int(metrics.get("domains_bootstrapped_u64", 0))))
            portfolio_obj = metrics.get("polymath_portfolio_score_q32")
            if isinstance(portfolio_obj, dict):
                portfolio_score_series.append(int(portfolio_obj.get("q", 0)))

    void_hash_changed_b = False
    for idx in range(1, len(void_hash_history)):
        if void_hash_history[idx] != void_hash_history[idx - 1]:
            void_hash_changed_b = True
            break

    conquer_improved_u64 = 0
    for path in sorted(
        state_dir.glob("subruns/**/daemon/rsi_polymath_conquer_domain_v1/state/reports/polymath_conquer_report_v1.json"),
        key=lambda row: row.as_posix(),
    ):
        payload = _load_json(path)
        if str(payload.get("status", "")) == "IMPROVED":
            conquer_improved_u64 += 1

    bootstrapped_reports_u64 = 0
    for path in sorted(
        state_dir.glob("subruns/**/daemon/rsi_polymath_bootstrap_domain_v1/state/reports/polymath_bootstrap_report_v1.json"),
        key=lambda row: row.as_posix(),
    ):
        payload = _load_json(path)
        if str(payload.get("status", "")).strip() == "BOOTSTRAPPED":
            bootstrapped_reports_u64 += 1

    domains_delta_u64 = 0
    domains_bootstrapped_first_u64 = 0
    domains_bootstrapped_last_u64 = 0
    if domains_bootstrapped_series:
        domains_bootstrapped_first_u64 = int(domains_bootstrapped_series[0])
        domains_bootstrapped_last_u64 = int(domains_bootstrapped_series[-1])
        domains_delta_u64 = max(0, int(domains_bootstrapped_last_u64) - int(domains_bootstrapped_first_u64))

    if portfolio_score_series:
        split_n = max(1, int(math.ceil(len(portfolio_score_series) * 0.20)))
        portfolio_score_early_q32 = int(statistics.median(portfolio_score_series[:split_n]))
        portfolio_score_late_q32 = int(statistics.median(portfolio_score_series[-split_n:]))
    else:
        portfolio_score_early_q32 = 0
        portfolio_score_late_q32 = 0

    gate_p_pass = bool(scout_dispatch_u64 > 0 and len(void_hash_history) > 0)
    gate_q_pass = bool(domains_delta_u64 > 0 or conquer_improved_u64 > 0 or bootstrapped_reports_u64 > 0)
    return {
        "gate_p_pass": gate_p_pass,
        "gate_q_pass": gate_q_pass,
        "scout_dispatch_u64": int(scout_dispatch_u64),
        "last_scout_tick_u64": int(scout_hash_stats.get("last_scout_tick_u64", 0)),
        "void_hash_history_u64": int(len(void_hash_history)),
        "void_hash_first": str(void_hash_history[0]) if void_hash_history else "",
        "void_hash_last": str(void_hash_history[-1]) if void_hash_history else "",
        "void_hash_changed_b": bool(void_hash_changed_b),
        "scout_dispatch_receipt_paths": list(scout_hash_stats.get("scout_dispatch_receipt_paths", [])),
        "scout_void_report_paths": list(scout_hash_stats.get("scout_void_report_paths", [])),
        "domains_bootstrapped_first_u64": int(domains_bootstrapped_first_u64),
        "domains_bootstrapped_last_u64": int(domains_bootstrapped_last_u64),
        "domains_bootstrapped_delta_u64": int(domains_delta_u64),
        "conquer_improved_u64": int(conquer_improved_u64),
        "bootstrapped_reports_u64": int(bootstrapped_reports_u64),
        "portfolio_score_early_q32": int(portfolio_score_early_q32),
        "portfolio_score_late_q32": int(portfolio_score_late_q32),
    }


def _perf_outcome_rows(state_dir: Path) -> list[dict[str, Any]]:
    perf_by_tick: dict[int, dict[str, Any]] = {}
    outcome_by_tick: dict[int, dict[str, Any]] = {}
    for path in sorted((state_dir / "perf").glob("sha256_*.omega_tick_perf_v1.json")):
        payload = _load_json(path)
        perf_by_tick[int(payload.get("tick_u64", -1))] = payload
    for path in sorted((state_dir / "perf").glob("sha256_*.omega_tick_outcome_v1.json")):
        payload = _load_json(path)
        outcome_by_tick[int(payload.get("tick_u64", -1))] = payload
    rows: list[dict[str, Any]] = []
    for tick_u64 in sorted(set(perf_by_tick.keys()) & set(outcome_by_tick.keys())):
        perf = perf_by_tick[tick_u64]
        outcome = outcome_by_tick[tick_u64]
        rows.append(
            {
                "tick_u64": tick_u64,
                "total_ns": max(0, int(perf.get("total_ns", 0))),
                "stps_total_q32": max(0, int(perf.get("stps_total_q32", 0))),
                "stps_non_noop_q32": max(0, int(perf.get("stps_non_noop_q32", 0))),
                "stps_promotion_q32": max(0, int(perf.get("stps_promotion_q32", 0))),
                "stps_activation_q32": max(0, int(perf.get("stps_activation_q32", 0))),
                "action_kind": str(outcome.get("action_kind", "")),
                "promotion_status": str(outcome.get("promotion_status", "")),
                "activation_success": bool(outcome.get("activation_success", False)),
                "activation_reasons": (
                    [str(row) for row in outcome.get("activation_reasons", [])]
                    if isinstance(outcome.get("activation_reasons"), list)
                    else []
                ),
                "activation_meta_verdict": (
                    str(outcome.get("activation_meta_verdict")).strip() or None
                    if outcome.get("activation_meta_verdict") is not None
                    else None
                ),
                "manifest_changed": bool(outcome.get("manifest_changed", False)),
            }
        )
    return rows


def _ticks_per_min(rows: list[dict[str, Any]], *, non_noop_only: bool = False, promoted_only: bool = False) -> float:
    selected = rows
    if non_noop_only:
        selected = [row for row in selected if str(row.get("action_kind", "")) != "NOOP"]
    if promoted_only:
        selected = [
            row
            for row in selected
            if str(row.get("promotion_status", "")) == "PROMOTED"
            and bool(row.get("activation_success", False))
            and bool(row.get("manifest_changed", False))
        ]
    total_ns = sum(int(row.get("total_ns", 0)) for row in selected)
    if total_ns <= 0:
        return 0.0
    return (len(selected) * 60_000_000_000.0) / float(total_ns)


def _median_q32(values: list[int]) -> int:
    if not values:
        return 0
    return int(statistics.median(values))


def _q32_to_float(value_q32: int) -> float:
    return float(int(value_q32)) / float(_Q32_ONE)


def _median_stps_non_noop_q32(rows: list[dict[str, Any]]) -> int:
    values = [max(0, int(row.get("stps_non_noop_q32", 0))) for row in rows if max(0, int(row.get("stps_non_noop_q32", 0))) > 0]
    return _median_q32(values)


def _stps_mode_rows(perf_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    modes = [
        ("NOOP", [row for row in perf_rows if str(row.get("action_kind", "")) == "NOOP"]),
        ("ACTIVE", [row for row in perf_rows if str(row.get("action_kind", "")) != "NOOP"]),
        ("PROMOTION", [row for row in perf_rows if str(row.get("promotion_status", "")) == "PROMOTED"]),
        ("ACTIVATION", [row for row in perf_rows if bool(row.get("activation_success", False))]),
    ]
    out: list[dict[str, Any]] = []
    for mode, rows in modes:
        out.append(
            {
                "mode": mode,
                "count_u64": int(len(rows)),
                "median_stps_total_q32": _median_q32([max(0, int(row.get("stps_total_q32", 0))) for row in rows]),
                "median_stps_non_noop_q32": _median_q32(
                    [max(0, int(row.get("stps_non_noop_q32", 0))) for row in rows if max(0, int(row.get("stps_non_noop_q32", 0))) > 0]
                ),
                "median_stps_promotion_q32": _median_q32(
                    [max(0, int(row.get("stps_promotion_q32", 0))) for row in rows if max(0, int(row.get("stps_promotion_q32", 0))) > 0]
                ),
                "median_stps_activation_q32": _median_q32(
                    [max(0, int(row.get("stps_activation_q32", 0))) for row in rows if max(0, int(row.get("stps_activation_q32", 0))) > 0]
                ),
            }
        )
    return out


def _median_non_noop_tpm(rows: list[dict[str, Any]]) -> float:
    samples: list[float] = []
    for row in rows:
        if str(row.get("action_kind", "")) == "NOOP":
            continue
        total_ns = max(0, int(row.get("total_ns", 0)))
        if total_ns <= 0:
            continue
        samples.append(60_000_000_000.0 / float(total_ns))
    if not samples:
        return 0.0
    return float(statistics.median(samples))


def _promotion_success_rate(rows: list[dict[str, Any]]) -> float:
    candidates = [row for row in rows if str(row.get("promotion_status", "")) in {"PROMOTED", "REJECTED"}]
    if not candidates:
        return 1.0
    successes = [
        row
        for row in candidates
        if str(row.get("promotion_status", "")) == "PROMOTED"
        and bool(row.get("activation_success", False))
        and bool(row.get("manifest_changed", False))
    ]
    return len(successes) / float(len(candidates))


def _gate_f_eval(
    *,
    ticks_completed: int,
    early_stps_non_noop_q32: int,
    late_stps_non_noop_q32: int,
    early_activation_successes: int,
    late_activation_successes: int,
) -> dict[str, Any]:
    gate_f_allowed_drop_pct = 0.10 if int(ticks_completed) <= 600 else 0.05
    allowed_keep_pct = int(round((1.0 - float(gate_f_allowed_drop_pct)) * 100.0))
    if int(early_stps_non_noop_q32) <= 0:
        gate_f_stps_non_regression_b = int(late_stps_non_noop_q32) > 0
    else:
        gate_f_stps_non_regression_b = int(late_stps_non_noop_q32) * 100 >= int(early_stps_non_noop_q32) * int(allowed_keep_pct)
    gate_f_activation_growth_b = int(late_activation_successes) > int(early_activation_successes)
    gate_f_pass = bool(gate_f_stps_non_regression_b or gate_f_activation_growth_b)
    gate_f_stps_regressed_b = not bool(gate_f_stps_non_regression_b)
    return {
        "gate_f_allowed_drop_pct": float(gate_f_allowed_drop_pct),
        "gate_f_stps_regressed_b": bool(gate_f_stps_regressed_b),
        "gate_f_stps_non_regression_b": bool(gate_f_stps_non_regression_b),
        "gate_f_activation_growth_b": bool(gate_f_activation_growth_b),
        "gate_f_pass": bool(gate_f_pass),
    }


def _evaluate_acceptance_gates(
    *,
    run_dir: Path,
    ticks_completed: int,
    pending_floor_u64: int,
    promotions_min_per_100_u64: int,
    promotion_summary: dict[str, Any],
    activation_live_mode: bool,
) -> dict[str, Any]:
    state_dir = _state_dir(run_dir)
    state_rows = _state_rows(state_dir)

    gate_a_rows = [row for row in state_rows if int(row.get("tick_u64", 0)) >= 20]
    gate_a_pairs: list[tuple[int, int, int]] = []
    for row in gate_a_rows:
        goals = row.get("goals") or {}
        if not isinstance(goals, dict):
            continue
        pending = sum(1 for value in goals.values() if isinstance(value, dict) and value.get("status") == "PENDING")
        done = sum(1 for value in goals.values() if isinstance(value, dict) and value.get("status") == "DONE")
        total_goals = sum(1 for value in goals.values() if isinstance(value, dict))
        required = min(int(pending_floor_u64), int(total_goals))
        gate_a_pairs.append((pending, done, required))
    gate_a_pass = bool(gate_a_pairs) and all(
        int(pending) >= int(required) or int(pending + done) >= int(required)
        for pending, done, required in gate_a_pairs
    )
    gate_a_min_pending = min((pending for pending, _, _ in gate_a_pairs), default=0)
    gate_a_min_available = min((pending + done for pending, done, _ in gate_a_pairs), default=0)
    gate_a_min_required = min((required for _, _, required in gate_a_pairs), default=0)

    promoted_u64 = int(promotion_summary.get("promoted_u64", 0))
    required_promotions = int(math.ceil((int(promotions_min_per_100_u64) * max(1, int(ticks_completed))) / 100.0))
    gate_b_pass = promoted_u64 >= required_promotions

    perf_rows = _perf_outcome_rows(state_dir)
    split_n = max(1, int(math.ceil(len(perf_rows) * 0.20))) if perf_rows else 1
    early_rows = perf_rows[:split_n]
    late_rows = perf_rows[-split_n:] if perf_rows else []

    early_non_noop_tpm = _median_non_noop_tpm(early_rows)
    late_non_noop_tpm = _median_non_noop_tpm(late_rows)
    early_success_rate = _promotion_success_rate(early_rows)
    late_success_rate = _promotion_success_rate(late_rows)
    if int(ticks_completed) < 300:
        gate_c_allowed_drop_pct = 0.10
    else:
        gate_c_allowed_drop_pct = 0.05
    gate_c_tpm_drop = late_non_noop_tpm < (early_non_noop_tpm * (1.0 - gate_c_allowed_drop_pct))
    gate_c_success_not_improving = late_success_rate <= early_success_rate
    gate_c_pass = not (gate_c_tpm_drop and gate_c_success_not_improving)

    early_stps_non_noop_q32 = _median_stps_non_noop_q32(early_rows)
    late_stps_non_noop_q32 = _median_stps_non_noop_q32(late_rows)
    early_activation_successes = sum(
        1 for row in early_rows if bool(row.get("activation_success", False)) and bool(row.get("manifest_changed", False))
    )
    late_activation_successes = sum(
        1 for row in late_rows if bool(row.get("activation_success", False)) and bool(row.get("manifest_changed", False))
    )
    gate_f_eval = _gate_f_eval(
        ticks_completed=int(ticks_completed),
        early_stps_non_noop_q32=int(early_stps_non_noop_q32),
        late_stps_non_noop_q32=int(late_stps_non_noop_q32),
        early_activation_successes=int(early_activation_successes),
        late_activation_successes=int(late_activation_successes),
    )
    gate_f_allowed_drop_pct = float(gate_f_eval.get("gate_f_allowed_drop_pct", 0.10))
    gate_f_stps_regressed_b = bool(gate_f_eval.get("gate_f_stps_regressed_b", False))
    gate_f_stps_non_regression_b = bool(gate_f_eval.get("gate_f_stps_non_regression_b", False))
    gate_f_activation_growth_b = bool(gate_f_eval.get("gate_f_activation_growth_b", False))
    gate_f_pass = bool(gate_f_eval.get("gate_f_pass", False))
    gate_f_required_uplift = 1.0

    activation_success_u64 = int(promotion_summary.get("activation_success_u64", 0))
    gate_d_pass = activation_success_u64 >= 1
    gate_d_status = "PASS" if activation_live_mode and gate_d_pass else ("FAIL" if activation_live_mode else "SKIP")

    unique_promotions_u64 = int(promotion_summary.get("unique_promotions_u64", 0))
    unique_activations_applied_u64 = int(promotion_summary.get("unique_activations_applied_u64", 0))
    unique_promoted_families_u64 = int(promotion_summary.get("unique_promoted_families_u64", 0))
    gate_e_pass = unique_promotions_u64 >= 6 and unique_promoted_families_u64 >= len(_SKILL_FAMILIES)

    polymath_stats = _polymath_gate_stats(run_dir)
    gate_p_pass = bool(polymath_stats.get("gate_p_pass", False))
    gate_q_pass = bool(polymath_stats.get("gate_q_pass", False))
    portfolio_score_early_q32 = int(polymath_stats.get("portfolio_score_early_q32", 0))
    portfolio_score_late_q32 = int(polymath_stats.get("portfolio_score_late_q32", 0))
    gate_r_pass = bool(
        (int(portfolio_score_late_q32) * 100) >= (int(portfolio_score_early_q32) * 98)
        or int(activation_success_u64) > 0
    )

    gate_status = {
        "A": "PASS" if gate_a_pass else "FAIL",
        "B": "PASS" if gate_b_pass else "FAIL",
        "C": "PASS" if gate_c_pass else "FAIL",
        "D": str(gate_d_status),
        "E": "PASS" if gate_e_pass else "FAIL",
        "F": "PASS" if gate_f_pass else "FAIL",
        "P": "PASS" if gate_p_pass else "FAIL",
        "Q": "PASS" if gate_q_pass else "FAIL",
        "R": "PASS" if gate_r_pass else "FAIL",
    }

    return {
        "gate_status": gate_status,
        "gate_a_min_pending": int(gate_a_min_pending),
        "gate_a_min_available": int(gate_a_min_available),
        "gate_a_min_required": int(gate_a_min_required),
        "required_promotions": int(required_promotions),
        "promoted_u64": int(promoted_u64),
        "activation_success_u64": int(activation_success_u64),
        "unique_promotions_u64": int(unique_promotions_u64),
        "unique_activations_applied_u64": int(unique_activations_applied_u64),
        "unique_promoted_families_u64": int(unique_promoted_families_u64),
        "stps_modes": _stps_mode_rows(perf_rows),
        "top_touched": list(promotion_summary.get("top_touched_paths") or []),
        "early_non_noop_tpm": float(early_non_noop_tpm),
        "late_non_noop_tpm": float(late_non_noop_tpm),
        "early_success_rate": float(early_success_rate),
        "late_success_rate": float(late_success_rate),
        "gate_c_allowed_drop_pct": float(gate_c_allowed_drop_pct),
        "early_stps_non_noop_q32": int(early_stps_non_noop_q32),
        "late_stps_non_noop_q32": int(late_stps_non_noop_q32),
        "gate_f_required_uplift": float(gate_f_required_uplift),
        "gate_f_allowed_drop_pct": float(gate_f_allowed_drop_pct),
        "gate_f_stps_regressed_b": bool(gate_f_stps_regressed_b),
        "gate_f_stps_non_regression_b": bool(gate_f_stps_non_regression_b),
        "gate_f_activation_growth_b": bool(gate_f_activation_growth_b),
        "early_activation_successes": int(early_activation_successes),
        "late_activation_successes": int(late_activation_successes),
        "polymath_stats": dict(polymath_stats),
        "portfolio_score_early_q32": int(portfolio_score_early_q32),
        "portfolio_score_late_q32": int(portfolio_score_late_q32),
        "median_stps_non_noop_full_run_q32": int(_median_stps_non_noop_q32(perf_rows)),
    }


def _build_gate_json_payload(
    *,
    series_prefix: str,
    run_dir: Path,
    ticks_completed: int,
    timings_agg: dict[str, Any],
    noop_counts: dict[str, Any],
    gate_eval: dict[str, Any],
    promotion_skip_reason_counts: dict[str, int],
) -> dict[str, Any]:
    noop_total_u64 = int(noop_counts.get("noop_total_u64", 0))
    runaway_blocked_noops_u64 = int((noop_counts.get("reason_counts") or {}).get("RUNAWAY_BLOCKED", 0))
    runaway_blocked_pct = (100.0 * runaway_blocked_noops_u64 / float(noop_total_u64)) if noop_total_u64 > 0 else 0.0
    gate_status = gate_eval.get("gate_status") if isinstance(gate_eval.get("gate_status"), dict) else {}
    polymath_stats = gate_eval.get("polymath_stats") if isinstance(gate_eval.get("polymath_stats"), dict) else {}
    normalized_skip_counts = _normalize_promotion_skip_reason_counts(promotion_skip_reason_counts)

    return {
        "schema_version": "OMEGA_BENCHMARK_GATES_v1",
        "created_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "series_prefix": str(series_prefix),
        "run_dir": run_dir.resolve().as_posix(),
        "ticks_completed_u64": int(ticks_completed),
        "non_noop_ticks_per_min": float(timings_agg.get("non_noop_ticks_per_min", 0.0)),
        "median_stps_non_noop_full_run": float(_q32_to_float(int(gate_eval.get("median_stps_non_noop_full_run_q32", 0)))),
        "runaway_blocked_noop_pct": float(runaway_blocked_pct),
        "gates": {
            "A": {"status": str(gate_status.get("A", "SKIP")), "details": {}},
            "B": {"status": str(gate_status.get("B", "SKIP")), "details": {}},
            "C": {
                "status": str(gate_status.get("C", "SKIP")),
                "details": {
                    "early_median_non_noop_tpm": float(gate_eval.get("early_non_noop_tpm", 0.0)),
                    "late_median_non_noop_tpm": float(gate_eval.get("late_non_noop_tpm", 0.0)),
                    "allowed_drop_pct": float(gate_eval.get("gate_c_allowed_drop_pct", 0.05)),
                    "early_promotion_success_rate": float(gate_eval.get("early_success_rate", 0.0)),
                    "late_promotion_success_rate": float(gate_eval.get("late_success_rate", 0.0)),
                },
            },
            "F": {
                "status": str(gate_status.get("F", "SKIP")),
                "details": {
                    "early_median_stps_non_noop": float(_q32_to_float(int(gate_eval.get("early_stps_non_noop_q32", 0)))),
                    "late_median_stps_non_noop": float(_q32_to_float(int(gate_eval.get("late_stps_non_noop_q32", 0)))),
                    "allowed_drop_pct": float(gate_eval.get("gate_f_allowed_drop_pct", 0.10)),
                    "required_uplift": float(gate_eval.get("gate_f_required_uplift", 1.0)),
                    "early_activation_successes": int(gate_eval.get("early_activation_successes", 0)),
                    "late_activation_successes": int(gate_eval.get("late_activation_successes", 0)),
                    "stps_non_regression_b": bool(gate_eval.get("gate_f_stps_non_regression_b", False)),
                    "activation_growth_b": bool(gate_eval.get("gate_f_activation_growth_b", False)),
                },
            },
            "P": {
                "status": str(gate_status.get("P", "SKIP")),
                "details": {
                    "scout_dispatch_u64": int(polymath_stats.get("scout_dispatch_u64", 0)),
                    "last_scout_tick_u64": int(polymath_stats.get("last_scout_tick_u64", 0)),
                    "void_hash_first": str(polymath_stats.get("void_hash_first", "")),
                    "void_hash_last": str(polymath_stats.get("void_hash_last", "")),
                    "void_hash_changed_b": bool(polymath_stats.get("void_hash_changed_b", False)),
                },
            },
            "Q": {
                "status": str(gate_status.get("Q", "SKIP")),
                "details": {
                    "domains_bootstrapped_first_u64": int(polymath_stats.get("domains_bootstrapped_first_u64", 0)),
                    "domains_bootstrapped_last_u64": int(polymath_stats.get("domains_bootstrapped_last_u64", 0)),
                    "domains_bootstrapped_delta_u64": int(polymath_stats.get("domains_bootstrapped_delta_u64", 0)),
                    "conquer_improved_u64": int(polymath_stats.get("conquer_improved_u64", 0)),
                    "bootstrapped_reports_u64": int(polymath_stats.get("bootstrapped_reports_u64", 0)),
                },
            },
            "R": {
                "status": str(gate_status.get("R", "SKIP")),
                "details": {
                    "portfolio_early_score_q32": int(gate_eval.get("portfolio_score_early_q32", 0)),
                    "portfolio_late_score_q32": int(gate_eval.get("portfolio_score_late_q32", 0)),
                },
            },
        },
        "promotion_skip_reason_counts": normalized_skip_counts,
    }


def _path_hash_rows(paths: list[Path]) -> list[dict[str, str]]:
    uniq: dict[str, Path] = {}
    for path in paths:
        resolved = path.resolve()
        uniq[resolved.as_posix()] = resolved
    out: list[dict[str, str]] = []
    for key in sorted(uniq.keys()):
        path = uniq[key]
        if not path.exists() or not path.is_file():
            continue
        out.append({"path": path.as_posix(), "sha256": hash_file_stream(path)})
    return out


def _build_gate_proof_payload(
    *,
    series_prefix: str,
    run_dir: Path,
    ticks_completed: int,
    gate_eval: dict[str, Any],
) -> dict[str, Any]:
    state_dir = _state_dir(run_dir)
    gate_status = gate_eval.get("gate_status") if isinstance(gate_eval.get("gate_status"), dict) else {}
    polymath_stats = gate_eval.get("polymath_stats") if isinstance(gate_eval.get("polymath_stats"), dict) else {}

    state_paths = sorted((state_dir / "state").glob("sha256_*.omega_state_v1.json"), key=lambda row: row.as_posix())
    observation_paths = sorted(
        (state_dir / "observations").glob("sha256_*.omega_observation_report_v1.json"),
        key=lambda row: row.as_posix(),
    )
    perf_tick_paths = sorted((state_dir / "perf").glob("sha256_*.omega_tick_perf_v1.json"), key=lambda row: row.as_posix())
    perf_outcome_paths = sorted(
        (state_dir / "perf").glob("sha256_*.omega_tick_outcome_v1.json"),
        key=lambda row: row.as_posix(),
    )
    promotion_paths = sorted(
        state_dir.glob("dispatch/*/promotion/sha256_*.omega_promotion_receipt_v1.json"),
        key=lambda row: row.as_posix(),
    )
    activation_paths = sorted(
        state_dir.glob("dispatch/*/activation/sha256_*.omega_activation_receipt_v1.json"),
        key=lambda row: row.as_posix(),
    )
    scout_dispatch_paths = [
        Path(str(path))
        for path in list(polymath_stats.get("scout_dispatch_receipt_paths", []))
        if str(path).strip()
    ]
    scout_void_paths = [
        Path(str(path))
        for path in list(polymath_stats.get("scout_void_report_paths", []))
        if str(path).strip()
    ]
    conquer_report_paths = sorted(
        state_dir.glob("subruns/**/daemon/rsi_polymath_conquer_domain_v1/state/reports/polymath_conquer_report_v1.json"),
        key=lambda row: row.as_posix(),
    )

    def _status(gate: str) -> str:
        return str(gate_status.get(gate, "SKIP"))

    gates = {
        "A": {
            "status": _status("A"),
            "inputs": {
                "state_rows": _path_hash_rows([Path(path) for path in state_paths]),
            },
            "intermediates": {
                "gate_a_min_pending": int(gate_eval.get("gate_a_min_pending", 0)),
                "gate_a_min_available": int(gate_eval.get("gate_a_min_available", 0)),
                "gate_a_min_required": int(gate_eval.get("gate_a_min_required", 0)),
            },
        },
        "B": {
            "status": _status("B"),
            "inputs": {
                "promotion_receipts": _path_hash_rows([Path(path) for path in promotion_paths]),
            },
            "intermediates": {
                "required_promotions": int(gate_eval.get("required_promotions", 0)),
                "promoted_u64": int(gate_eval.get("promoted_u64", 0)),
            },
        },
        "C": {
            "status": _status("C"),
            "inputs": {
                "tick_perf": _path_hash_rows([Path(path) for path in perf_tick_paths]),
                "tick_outcome": _path_hash_rows([Path(path) for path in perf_outcome_paths]),
            },
            "intermediates": {
                "early_non_noop_tpm": float(gate_eval.get("early_non_noop_tpm", 0.0)),
                "late_non_noop_tpm": float(gate_eval.get("late_non_noop_tpm", 0.0)),
                "early_success_rate": float(gate_eval.get("early_success_rate", 0.0)),
                "late_success_rate": float(gate_eval.get("late_success_rate", 0.0)),
                "gate_c_allowed_drop_pct": float(gate_eval.get("gate_c_allowed_drop_pct", 0.05)),
            },
        },
        "D": {
            "status": _status("D"),
            "inputs": {
                "activation_receipts": _path_hash_rows([Path(path) for path in activation_paths]),
            },
            "intermediates": {
                "activation_success_u64": int(gate_eval.get("activation_success_u64", 0)),
            },
        },
        "E": {
            "status": _status("E"),
            "inputs": {
                "promotion_receipts": _path_hash_rows([Path(path) for path in promotion_paths]),
            },
            "intermediates": {
                "unique_promotions_u64": int(gate_eval.get("unique_promotions_u64", 0)),
                "unique_promoted_families_u64": int(gate_eval.get("unique_promoted_families_u64", 0)),
            },
        },
        "F": {
            "status": _status("F"),
            "inputs": {
                "tick_perf": _path_hash_rows([Path(path) for path in perf_tick_paths]),
                "tick_outcome": _path_hash_rows([Path(path) for path in perf_outcome_paths]),
            },
            "intermediates": {
                "early_stps_non_noop_q32": int(gate_eval.get("early_stps_non_noop_q32", 0)),
                "late_stps_non_noop_q32": int(gate_eval.get("late_stps_non_noop_q32", 0)),
                "early_activation_successes": int(gate_eval.get("early_activation_successes", 0)),
                "late_activation_successes": int(gate_eval.get("late_activation_successes", 0)),
                "gate_f_allowed_drop_pct": float(gate_eval.get("gate_f_allowed_drop_pct", 0.10)),
            },
        },
        "P": {
            "status": _status("P"),
            "inputs": {
                "scout_dispatch_receipts": _path_hash_rows(scout_dispatch_paths),
                "scout_void_reports": _path_hash_rows(scout_void_paths),
                "observation_rows": _path_hash_rows([Path(path) for path in observation_paths]),
            },
            "intermediates": {
                "scout_dispatch_u64": int(polymath_stats.get("scout_dispatch_u64", 0)),
                "last_scout_tick_u64": int(polymath_stats.get("last_scout_tick_u64", 0)),
                "void_hash_history_u64": int(polymath_stats.get("void_hash_history_u64", 0)),
                "void_hash_first": str(polymath_stats.get("void_hash_first", "")),
                "void_hash_last": str(polymath_stats.get("void_hash_last", "")),
                "void_hash_changed_b": bool(polymath_stats.get("void_hash_changed_b", False)),
            },
        },
        "Q": {
            "status": _status("Q"),
            "inputs": {
                "observation_rows": _path_hash_rows([Path(path) for path in observation_paths]),
                "conquer_reports": _path_hash_rows([Path(path) for path in conquer_report_paths]),
            },
            "intermediates": {
                "domains_bootstrapped_first_u64": int(polymath_stats.get("domains_bootstrapped_first_u64", 0)),
                "domains_bootstrapped_last_u64": int(polymath_stats.get("domains_bootstrapped_last_u64", 0)),
                "domains_bootstrapped_delta_u64": int(polymath_stats.get("domains_bootstrapped_delta_u64", 0)),
                "conquer_improved_u64": int(polymath_stats.get("conquer_improved_u64", 0)),
                "bootstrapped_reports_u64": int(polymath_stats.get("bootstrapped_reports_u64", 0)),
            },
        },
        "R": {
            "status": _status("R"),
            "inputs": {
                "observation_rows": _path_hash_rows([Path(path) for path in observation_paths]),
            },
            "intermediates": {
                "portfolio_score_early_q32": int(gate_eval.get("portfolio_score_early_q32", 0)),
                "portfolio_score_late_q32": int(gate_eval.get("portfolio_score_late_q32", 0)),
            },
        },
    }

    return {
        "schema_version": "OMEGA_GATE_PROOF_v1",
        "created_at_utc": "",
        "created_from_tick_u64": int(ticks_completed),
        "series_prefix": str(series_prefix),
        "run_dir": run_dir.resolve().as_posix(),
        "ticks_completed_u64": int(ticks_completed),
        "gates": gates,
    }


def _build_markdown_summary(
    *,
    series_prefix: str,
    run_dir: Path,
    ticks_completed: int,
    pending_floor_u64: int,
    promotions_min_per_100_u64: int,
    timings_agg: dict[str, Any],
    noop_counts: dict[str, Any],
    promotion_summary: dict[str, Any],
    activation_live_mode: bool,
    gate_eval: dict[str, Any] | None = None,
) -> str:
    noop_total_u64 = int(noop_counts.get("noop_total_u64", 0))
    runaway_blocked_noops_u64 = int((noop_counts.get("reason_counts") or {}).get("RUNAWAY_BLOCKED", 0))
    runaway_blocked_pct = (100.0 * runaway_blocked_noops_u64 / float(noop_total_u64)) if noop_total_u64 > 0 else 0.0

    if gate_eval is None:
        gate_eval = _evaluate_acceptance_gates(
            run_dir=run_dir,
            ticks_completed=ticks_completed,
            pending_floor_u64=pending_floor_u64,
            promotions_min_per_100_u64=promotions_min_per_100_u64,
            promotion_summary=promotion_summary,
            activation_live_mode=activation_live_mode,
        )

    gate_status = gate_eval.get("gate_status") if isinstance(gate_eval.get("gate_status"), dict) else {}
    gate_a_pass = str(gate_status.get("A", "FAIL")) == "PASS"
    gate_b_pass = str(gate_status.get("B", "FAIL")) == "PASS"
    gate_c_pass = str(gate_status.get("C", "FAIL")) == "PASS"
    gate_d_status = str(gate_status.get("D", "SKIP"))
    gate_e_pass = str(gate_status.get("E", "FAIL")) == "PASS"
    gate_f_pass = str(gate_status.get("F", "FAIL")) == "PASS"
    gate_p_pass = str(gate_status.get("P", "FAIL")) == "PASS"
    gate_q_pass = str(gate_status.get("Q", "FAIL")) == "PASS"
    gate_r_pass = str(gate_status.get("R", "FAIL")) == "PASS"

    promoted_u64 = int(gate_eval.get("promoted_u64", 0))
    required_promotions = int(gate_eval.get("required_promotions", 0))
    activation_success_u64 = int(gate_eval.get("activation_success_u64", 0))
    unique_promotions_u64 = int(gate_eval.get("unique_promotions_u64", 0))
    unique_activations_applied_u64 = int(gate_eval.get("unique_activations_applied_u64", 0))
    unique_promoted_families_u64 = int(gate_eval.get("unique_promoted_families_u64", 0))
    stps_modes = list(gate_eval.get("stps_modes") or [])
    top_touched = list(gate_eval.get("top_touched") or [])
    early_non_noop_tpm = float(gate_eval.get("early_non_noop_tpm", 0.0))
    late_non_noop_tpm = float(gate_eval.get("late_non_noop_tpm", 0.0))
    early_success_rate = float(gate_eval.get("early_success_rate", 0.0))
    late_success_rate = float(gate_eval.get("late_success_rate", 0.0))
    early_stps_non_noop_q32 = int(gate_eval.get("early_stps_non_noop_q32", 0))
    late_stps_non_noop_q32 = int(gate_eval.get("late_stps_non_noop_q32", 0))
    gate_f_allowed_drop_pct = float(gate_eval.get("gate_f_allowed_drop_pct", 0.10))
    gate_f_stps_non_regression_b = bool(gate_eval.get("gate_f_stps_non_regression_b", False))
    gate_f_activation_growth_b = bool(gate_eval.get("gate_f_activation_growth_b", False))
    early_activation_successes = int(gate_eval.get("early_activation_successes", 0))
    late_activation_successes = int(gate_eval.get("late_activation_successes", 0))
    polymath_stats = gate_eval.get("polymath_stats") if isinstance(gate_eval.get("polymath_stats"), dict) else {}
    portfolio_score_early_q32 = int(gate_eval.get("portfolio_score_early_q32", 0))
    portfolio_score_late_q32 = int(gate_eval.get("portfolio_score_late_q32", 0))
    gate_a_min_pending = int(gate_eval.get("gate_a_min_pending", 0))
    gate_a_min_available = int(gate_eval.get("gate_a_min_available", 0))
    gate_a_min_required = int(gate_eval.get("gate_a_min_required", 0))
    top_touched_lines = "\n".join(
        f"- `{row.get('path', '')}`: {int(row.get('count_u64', 0))}"
        for row in top_touched[:10]
    )
    if not top_touched_lines:
        top_touched_lines = "- (none)"

    lines = [
        f"# OMEGA Benchmark Summary ({series_prefix})",
        "",
        f"- Ticks completed: **{int(ticks_completed)}**",
        f"- Non-NOOP ticks/min: **{float(timings_agg.get('non_noop_ticks_per_min', 0.0)):.4f}**",
        f"- Promotions/min: **{float(timings_agg.get('promotion_ticks_per_min', 0.0)):.4f}**",
        f"- % RUNAWAY_BLOCKED NOOP: **{runaway_blocked_pct:.2f}%**",
        f"- Promotions: **{promoted_u64}**",
        f"- Activation successes: **{activation_success_u64}**",
        f"- Activation denied: **{int(promotion_summary.get('activation_denied_u64', 0))}**",
        f"- Pointer swap failed: **{int(promotion_summary.get('activation_pointer_swap_failed_u64', 0))}**",
        f"- Binding mismatch: **{int(promotion_summary.get('activation_binding_mismatch_u64', 0))}**",
        f"- Unique promoted (capability_id, activation_key): **{unique_promotions_u64}**",
        f"- Unique activations applied: **{unique_activations_applied_u64}**",
        (
            "- Median STPS (non-NOOP, full run): "
            f"**{_q32_to_float(int(gate_eval.get('median_stps_non_noop_full_run_q32', 0))):.6f}**"
        ),
        "",
        "## STPS By Mode",
        "| Mode | Count | Median STPS(total) | Median STPS(non-noop) | Median STPS(promotion) | Median STPS(activation) |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        *[
            "| "
            f"{row['mode']} | {int(row['count_u64'])} | "
            f"{_q32_to_float(int(row['median_stps_total_q32'])):.6f} | "
            f"{_q32_to_float(int(row['median_stps_non_noop_q32'])):.6f} | "
            f"{_q32_to_float(int(row['median_stps_promotion_q32'])):.6f} | "
            f"{_q32_to_float(int(row['median_stps_activation_q32'])):.6f} |"
            for row in stps_modes
        ],
        "",
        "## Top Touched Paths",
        top_touched_lines,
        "",
        "## Acceptance Gates",
        "- Gate A (pending or pending+done goals after tick 20 >= min(config floor, effective goal count)): "
        f"**{'PASS' if gate_a_pass else 'FAIL'}**",
        f"- Gate B (promotions >= {required_promotions} for {int(ticks_completed)} ticks): **{'PASS' if gate_b_pass else 'FAIL'}**",
        "- Gate C (last-20% median non-noop TPM may drop by >5% only if promotion success is not improving): "
        f"**{'PASS' if gate_c_pass else 'FAIL'}**",
        f"- Gate D (activation successes >= 1 in live mode): **{gate_d_status}**",
        "- Gate E (>=6 unique promotions spanning CODE/SYSTEM/KERNEL/METASEARCH/VAL/SCIENCE): "
        f"**{'PASS' if gate_e_pass else 'FAIL'}**",
        "- Gate F (last-20% median STPS(non-noop) does not regress beyond allowed drop OR activation successes increased): "
        f"**{'PASS' if gate_f_pass else 'FAIL'}**",
        "- Gate P (scout ran >=1 and produced non-empty deterministic void-hash evidence): "
        f"**{'PASS' if gate_p_pass else 'FAIL'}**",
        "- Gate Q (domains bootstrapped increased OR conquer metric improved at least once): "
        f"**{'PASS' if gate_q_pass else 'FAIL'}**",
        "- Gate R (portfolio score late-window >= early-window * 0.98 OR any activation success): "
        f"**{'PASS' if gate_r_pass else 'FAIL'}**",
        "",
        f"- Gate C early median non-noop TPM: **{early_non_noop_tpm:.4f}**",
        f"- Gate C late median non-noop TPM: **{late_non_noop_tpm:.4f}**",
        f"- Gate C early promotion success rate: **{early_success_rate:.4f}**",
        f"- Gate C late promotion success rate: **{late_success_rate:.4f}**",
        f"- Gate F early median STPS(non-noop): **{_q32_to_float(early_stps_non_noop_q32):.6f}**",
        f"- Gate F late median STPS(non-noop): **{_q32_to_float(late_stps_non_noop_q32):.6f}**",
        f"- Gate F allowed drop pct: **{gate_f_allowed_drop_pct:.2f}**",
        f"- Gate F stps_non_regression_b: **{gate_f_stps_non_regression_b}**",
        f"- Gate F activation_growth_b: **{gate_f_activation_growth_b}**",
        f"- Gate F early activation successes (first 20%): **{int(early_activation_successes)}**",
        f"- Gate F late activation successes (last 20%): **{int(late_activation_successes)}**",
        f"- Gate E unique promoted families: **{unique_promoted_families_u64}**",
        f"- Gate P scout dispatch count: **{int(polymath_stats.get('scout_dispatch_u64', 0))}**",
        f"- Gate P void-hash changed: **{bool(polymath_stats.get('void_hash_changed_b', False))}**",
        f"- Gate Q domains_bootstrapped delta: **{int(polymath_stats.get('domains_bootstrapped_delta_u64', 0))}**",
        f"- Gate Q conquer improved reports: **{int(polymath_stats.get('conquer_improved_u64', 0))}**",
        f"- Gate Q bootstrap report count: **{int(polymath_stats.get('bootstrapped_reports_u64', 0))}**",
        f"- Gate R portfolio early score q32: **{int(portfolio_score_early_q32)}**",
        f"- Gate R portfolio late score q32: **{int(portfolio_score_late_q32)}**",
        f"- Gate A min pending goals: **{gate_a_min_pending}**",
        f"- Gate A min pending+done goals: **{gate_a_min_available}** (required min: **{gate_a_min_required}**)",
        "",
    ]

    if activation_success_u64 == 0:
        reason_rows = promotion_summary.get("activation_failure_reason_counts") or []
        lines.extend(
            [
                "## Top Activation Failure Reasons",
                "| Reason | Count |",
                "| --- | ---: |",
            ]
        )
        if reason_rows:
            for row in reason_rows[:10]:
                lines.append(f"| `{row.get('reason', '')}` | {int(row.get('count_u64', 0))} |")
        else:
            lines.append("| (none) | 0 |")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(prog="omega_benchmark_suite_v19_v1")
    parser.add_argument("--ticks", type=int, default=100)
    parser.add_argument("--seed_u64", type=int, default=424242)
    parser.add_argument("--runs_root", default="runs")
    parser.add_argument("--series_prefix", default="")
    parser.add_argument("--existing_run_dir", default="")
    parser.add_argument("--pending_floor_u64", type=int, default=24)
    parser.add_argument("--promotions_min_per_100_u64", type=int, default=1)
    parser.add_argument("--keep_base_goal_queue", action="store_true")
    parser.add_argument("--no_simulate_activation", action="store_true")
    args = parser.parse_args()

    existing_run_dir_raw = str(args.existing_run_dir).strip()
    existing_run_dir = Path(existing_run_dir_raw).resolve() if existing_run_dir_raw else None
    if existing_run_dir is not None:
        run_dir = existing_run_dir
        if not run_dir.exists() or not run_dir.is_dir():
            raise FileNotFoundError(f"missing run directory: {run_dir}")
        runs_root = run_dir.parent
        series_prefix = run_dir.name
        state_rows = _state_rows(_state_dir(run_dir))
        ticks_completed = max((int(row.get("tick_u64", 0)) for row in state_rows), default=0)
    else:
        runs_root = Path(args.runs_root).resolve()
        runs_root.mkdir(parents=True, exist_ok=True)
        series_prefix = str(args.series_prefix).strip()
        if not series_prefix:
            ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            series_prefix = f"rsi_omega_benchmark_v19_0_{ts}"
        run_dir = runs_root / series_prefix
        shutil.rmtree(run_dir, ignore_errors=True)
        run_dir.mkdir(parents=True, exist_ok=True)

        campaign_pack = _prepare_campaign_pack(
            run_dir=run_dir,
            make_base_goal_queue_empty=not bool(args.keep_base_goal_queue),
        )

        os.environ["OMEGA_RUN_SEED_U64"] = str(int(args.seed_u64))
        os.environ["OMEGA_V19_DETERMINISTIC_TIMING"] = "1"
        if not bool(args.no_simulate_activation):
            os.environ["OMEGA_META_CORE_ACTIVATION_MODE"] = "simulate"
            os.environ["OMEGA_ALLOW_SIMULATE_ACTIVATION"] = "1"

        ticks_completed = _run_tick_loop(
            campaign_pack=campaign_pack,
            run_dir=run_dir,
            ticks=max(1, int(args.ticks)),
        )

    timings_path = run_dir / "OMEGA_TIMINGS_AGG_v1.json"
    noop_path = run_dir / "OMEGA_NOOP_REASON_COUNTS_v1.json"
    timings_ok = _run_tool(
        _REPO_ROOT / "tools" / "omega" / "omega_timings_aggregate_v1.py",
        series_prefix=series_prefix,
        runs_root=runs_root,
        out_path=timings_path,
    )
    noop_ok = _run_tool(
        _REPO_ROOT / "tools" / "omega" / "omega_noop_reason_classifier_v1.py",
        series_prefix=series_prefix,
        runs_root=runs_root,
        out_path=noop_path,
    )
    if not timings_ok or not timings_path.exists():
        _write_json(
            timings_path,
            {
                "schema_version": "OMEGA_TIMINGS_AGG_v1",
                "series_prefix": series_prefix,
                "runs_root": runs_root.as_posix(),
                "ticks_scanned_u64": 0,
                "runs_scanned_u64": 0,
                "non_noop_ticks_per_min": 0.0,
                "promotion_ticks_per_min": 0.0,
            },
        )
    if not noop_ok or not noop_path.exists():
        _write_json(
            noop_path,
            {
                "schema_version": "OMEGA_NOOP_REASON_COUNTS_v1",
                "series_prefix": series_prefix,
                "runs_root": runs_root.as_posix(),
                "noop_total_u64": 0,
                "reason_counts": {},
                "noop_rows": [],
            },
        )

    perf_dir = _state_dir(run_dir) / "perf"
    latest_scorecard = _latest_payload(perf_dir, "omega_run_scorecard_v1.json")
    if latest_scorecard is None:
        latest_scorecard = {
            "schema_version": "omega_run_scorecard_v1",
            "tick_u64": 0,
            "window_size_u64": 32,
            "window_rows": [],
            "run_ticks_u64": 0,
            "non_noop_ticks_u64": 0,
            "promotion_success_u64": 0,
            "promotion_reject_candidates_u64": 0,
            "total_ns_u64": 0,
            "non_noop_tpm_rat": {"num_u64": 0, "den_u64": 1},
            "promotion_tpm_rat": {"num_u64": 0, "den_u64": 1},
            "avg_dispatch_ns_u64": 0,
            "avg_subverifier_ns_u64": 0,
            "avg_promotion_ns_u64": 0,
            "median_stps_total_q32": 0,
            "median_stps_non_noop_q32": 0,
            "median_stps_promotion_q32": 0,
            "median_stps_activation_q32": 0,
            "promotion_success_rate_rat": {"num_u64": 0, "den_u64": 1},
            "runaway_blocked_noop_rate_rat": {"num_u64": 0, "den_u64": 1},
            "goals_by_capability": {},
        }
    _write_json(run_dir / "OMEGA_RUN_SCORECARD_v1.json", latest_scorecard)

    promotion_summary = _promotion_summary(run_dir=run_dir, series_prefix=series_prefix, runs_root=runs_root)
    _write_json(run_dir / "OMEGA_PROMOTION_SUMMARY_v1.json", promotion_summary)

    timings_agg = _load_json(timings_path)
    noop_counts = _load_json(noop_path)
    gate_eval = _evaluate_acceptance_gates(
        run_dir=run_dir,
        ticks_completed=ticks_completed,
        pending_floor_u64=int(args.pending_floor_u64),
        promotions_min_per_100_u64=int(args.promotions_min_per_100_u64),
        promotion_summary=promotion_summary,
        activation_live_mode=bool(args.no_simulate_activation),
    )
    gate_json_payload = _build_gate_json_payload(
        series_prefix=series_prefix,
        run_dir=run_dir,
        ticks_completed=ticks_completed,
        timings_agg=timings_agg,
        noop_counts=noop_counts,
        gate_eval=gate_eval,
        promotion_skip_reason_counts=promotion_summary.get("promotion_skip_reason_counts", {}),
    )
    gate_json_path = run_dir / "OMEGA_BENCHMARK_GATES_v1.json"
    _write_json(gate_json_path, gate_json_payload)
    gate_proof_payload = _build_gate_proof_payload(
        series_prefix=series_prefix,
        run_dir=run_dir,
        ticks_completed=ticks_completed,
        gate_eval=gate_eval,
    )
    gate_proof_path = run_dir / "OMEGA_GATE_PROOF_v1.json"
    _write_json(gate_proof_path, gate_proof_payload)
    summary_md = _build_markdown_summary(
        series_prefix=series_prefix,
        run_dir=run_dir,
        ticks_completed=ticks_completed,
        pending_floor_u64=int(args.pending_floor_u64),
        promotions_min_per_100_u64=int(args.promotions_min_per_100_u64),
        timings_agg=timings_agg,
        noop_counts=noop_counts,
        promotion_summary=promotion_summary,
        activation_live_mode=bool(args.no_simulate_activation),
        gate_eval=gate_eval,
    )
    summary_path = run_dir / "OMEGA_BENCHMARK_SUMMARY_v1.md"
    _write_md(summary_path, summary_md)

    print((run_dir / "OMEGA_TIMINGS_AGG_v1.json").as_posix())
    print((run_dir / "OMEGA_NOOP_REASON_COUNTS_v1.json").as_posix())
    print((run_dir / "OMEGA_RUN_SCORECARD_v1.json").as_posix())
    print((run_dir / "OMEGA_PROMOTION_SUMMARY_v1.json").as_posix())
    print(gate_json_path.as_posix())
    print(gate_proof_path.as_posix())
    print(summary_path.as_posix())


if __name__ == "__main__":
    main()
