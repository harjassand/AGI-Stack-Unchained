#!/usr/bin/env python3
"""Emit OMEGA_BENCHMARK_GATES_v1.json for v19 loop runs.

This is the v19 analogue of the benchmark gate truth artifact used by
tools/omega/omega_gate_loader_v1.py, which prefers JSON over Markdown.

We compute only gates A/P/Q, using the same evidence rules as
tools/omega/omega_benchmark_suite_v1.py, but over the per-tick run
directories produced by tools/v19_runs/run_omega_v19_full_loop.py.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

_TICK_DIR_RE = re.compile(r"^tick_(\d+)$")
_DAEMON_ID = "rsi_omega_daemon_v19_0"
_SCOUT_CAMPAIGN_ID = "rsi_polymath_scout_v1"
_PENDING_FLOOR_U64_DEFAULT = 24


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_load_dict(path: Path, *, errors: list[str], context: str) -> dict[str, Any] | None:
    try:
        payload = _load_json(path)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"INVALID_JSON:{context}:{path.as_posix()}:{type(exc).__name__}")
        return None
    if not isinstance(payload, dict):
        errors.append(f"NOT_OBJECT:{context}:{path.as_posix()}")
        return None
    return payload


def _hash_file_stream(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(4 * 1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return f"sha256:{hasher.hexdigest()}"


def _load_jsonl_best_effort(path: Path, *, errors: list[str], context: str) -> list[dict[str, Any]]:
    if not path.exists() or not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for idx, raw in enumerate(path.read_text(encoding="utf-8").splitlines()):
        raw = raw.strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"INVALID_JSONL:{context}:{path.as_posix()}:{idx}:{type(exc).__name__}")
            continue
        if not isinstance(payload, dict):
            errors.append(f"JSONL_NOT_OBJECT:{context}:{path.as_posix()}:{idx}")
            continue
        out.append(payload)
    return out


def _state_dir(run_dir: Path) -> Path:
    return run_dir / "daemon" / _DAEMON_ID / "state"


def _tick_run_dirs(runs_root: Path) -> list[tuple[int, Path]]:
    runs_root = runs_root.resolve()
    out: list[tuple[int, Path]] = []
    for child in sorted(runs_root.iterdir(), key=lambda row: row.as_posix()):
        if not child.is_dir():
            continue
        match = _TICK_DIR_RE.match(child.name)
        if not match:
            continue
        out.append((int(match.group(1)), child))
    if out:
        out.sort(key=lambda row: int(row[0]))
        return out
    # Fallback: treat runs_root itself as a single run dir (useful for one-off debugging).
    return [(0, runs_root)]


def _iter_state_paths(state_dir: Path) -> list[Path]:
    candidates: list[Path] = []
    if (state_dir / "state").is_dir():
        candidates.extend(sorted((state_dir / "state").glob("sha256_*.omega_state_v1.json"), key=lambda row: row.as_posix()))
    candidates.extend(sorted(state_dir.glob("sha256_*.omega_state_v1.json"), key=lambda row: row.as_posix()))
    return candidates


def _iter_observation_paths(state_dir: Path) -> list[Path]:
    obs_dir = state_dir / "observations"
    if not obs_dir.exists() or not obs_dir.is_dir():
        return []
    return sorted(obs_dir.glob("sha256_*.omega_observation_report_v1.json"), key=lambda row: row.as_posix())


def _load_state_rows(*, runs_root: Path, errors: list[str]) -> list[dict[str, Any]]:
    state_by_tick: dict[int, dict[str, Any]] = {}
    for _tick_id, run_dir in _tick_run_dirs(runs_root):
        state_dir = _state_dir(run_dir)
        for state_path in _iter_state_paths(state_dir):
            payload = _safe_load_dict(state_path, errors=errors, context="omega_state_v1")
            if payload is None:
                continue
            try:
                tick_u64 = int(payload.get("tick_u64", -1))
            except Exception:  # noqa: BLE001
                continue
            if tick_u64 < 0:
                continue
            # If multiple snapshots exist, keep the lexicographically-latest path for determinism.
            existing = state_by_tick.get(tick_u64)
            if existing is None or state_path.as_posix() >= str(existing.get("_source_path", "")):
                payload = dict(payload)
                payload["_source_path"] = state_path.as_posix()
                state_by_tick[tick_u64] = payload
    return [state_by_tick[t] for t in sorted(state_by_tick.keys())]


def _observation_rows(*, runs_root: Path, errors: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _tick_id, run_dir in _tick_run_dirs(runs_root):
        state_dir = _state_dir(run_dir)
        for path in _iter_observation_paths(state_dir):
            payload = _safe_load_dict(path, errors=errors, context="omega_observation_report_v1")
            if payload is None:
                continue
            try:
                tick_u64 = int(payload.get("tick_u64", -1))
            except Exception:  # noqa: BLE001
                continue
            if tick_u64 < 0:
                continue
            payload = dict(payload)
            payload["_source_path"] = path.as_posix()
            rows.append(payload)
    rows.sort(key=lambda row: (int(row.get("tick_u64", 0)), str(row.get("_source_path", ""))))
    return rows


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


def _scout_dispatch_void_hash_history(*, runs_root: Path, errors: list[str]) -> dict[str, Any]:
    scout_rows: list[tuple[int, str, Path]] = []
    scout_dispatch_u64 = 0
    last_scout_tick_u64 = 0

    for _tick_id, run_dir in _tick_run_dirs(runs_root):
        state_dir = _state_dir(run_dir)
        dispatch_paths = sorted(
            state_dir.glob("dispatch/*/sha256_*.omega_dispatch_receipt_v1.json"),
            key=lambda row: row.as_posix(),
        )
        for path in dispatch_paths:
            payload = _safe_load_dict(path, errors=errors, context="omega_dispatch_receipt_v1")
            if payload is None:
                continue
            if str(payload.get("campaign_id", "")) != _SCOUT_CAMPAIGN_ID:
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
        rows = _load_jsonl_best_effort(void_path, errors=errors, context="polymath_void_report_v1_jsonl")
        if not rows:
            continue
        void_hash_history.append(_hash_file_stream(void_path))

    return {
        "scout_dispatch_u64": int(scout_dispatch_u64),
        "last_scout_tick_u64": int(last_scout_tick_u64),
        "void_hash_history": list(void_hash_history),
        "scout_dispatch_receipt_paths": sorted(set(str(row[1]) for row in scout_rows)),
        "scout_void_report_paths": sorted(set(path.as_posix() for _, _, path in scout_rows)),
    }


def _polymath_gate_stats(*, runs_root: Path, errors: list[str]) -> dict[str, Any]:
    observation_rows = _observation_rows(runs_root=runs_root, errors=errors)

    scout_hash_stats = _scout_dispatch_void_hash_history(runs_root=runs_root, errors=errors)
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

    void_hash_changed_b = False
    for idx in range(1, len(void_hash_history)):
        if void_hash_history[idx] != void_hash_history[idx - 1]:
            void_hash_changed_b = True
            break

    domains_bootstrapped_series: list[int] = []
    for row in observation_rows:
        metrics = row.get("metrics")
        if not isinstance(metrics, dict):
            continue
        domains_bootstrapped_series.append(max(0, int(metrics.get("domains_bootstrapped_u64", 0))))

    domains_bootstrapped_first_u64 = int(domains_bootstrapped_series[0]) if domains_bootstrapped_series else 0
    domains_bootstrapped_last_u64 = int(domains_bootstrapped_series[-1]) if domains_bootstrapped_series else 0
    domains_delta_u64 = (
        max(0, domains_bootstrapped_last_u64 - domains_bootstrapped_first_u64) if domains_bootstrapped_series else 0
    )

    conquer_improved_u64 = 0
    bootstrapped_reports_u64 = 0
    for _tick_id, run_dir in _tick_run_dirs(runs_root):
        state_dir = _state_dir(run_dir)
        for path in sorted(
            state_dir.glob("subruns/**/daemon/rsi_polymath_conquer_domain_v1/state/reports/polymath_conquer_report_v1.json"),
            key=lambda row: row.as_posix(),
        ):
            payload = _safe_load_dict(path, errors=errors, context="polymath_conquer_report_v1")
            if payload is None:
                continue
            if str(payload.get("status", "")).strip() == "IMPROVED":
                conquer_improved_u64 += 1
        for path in sorted(
            state_dir.glob("subruns/**/daemon/rsi_polymath_bootstrap_domain_v1/state/reports/polymath_bootstrap_report_v1.json"),
            key=lambda row: row.as_posix(),
        ):
            payload = _safe_load_dict(path, errors=errors, context="polymath_bootstrap_report_v1")
            if payload is None:
                continue
            if str(payload.get("status", "")).strip() == "BOOTSTRAPPED":
                bootstrapped_reports_u64 += 1

    gate_p_pass = bool(scout_dispatch_u64 > 0 and len(void_hash_history) > 0)
    gate_q_pass = bool(domains_delta_u64 > 0 or conquer_improved_u64 > 0 or bootstrapped_reports_u64 > 0)

    return {
        "gate_p_pass": bool(gate_p_pass),
        "gate_q_pass": bool(gate_q_pass),
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
        # Alias for callers that expect the shorter name.
        "domains_delta_u64": int(domains_delta_u64),
        "conquer_improved_u64": int(conquer_improved_u64),
        "bootstrapped_reports_u64": int(bootstrapped_reports_u64),
    }


def build_gate_payload(*, runs_root: Path, pending_floor_u64: int = _PENDING_FLOOR_U64_DEFAULT) -> dict[str, Any]:
    runs_root = runs_root.resolve()
    errors: list[str] = []

    tick_dirs = _tick_run_dirs(runs_root)
    latest_tick_id, latest_run_dir = max(tick_dirs, key=lambda row: int(row[0]))

    state_rows = _load_state_rows(runs_root=runs_root, errors=errors)
    gate_a_rows = [row for row in state_rows if int(row.get("tick_u64", 0)) >= 20]
    gate_a_pairs: list[dict[str, int]] = []
    for row in gate_a_rows:
        goals = row.get("goals") or {}
        if not isinstance(goals, dict):
            continue
        pending = sum(1 for value in goals.values() if isinstance(value, dict) and value.get("status") == "PENDING")
        done = sum(1 for value in goals.values() if isinstance(value, dict) and value.get("status") == "DONE")
        total_goals = sum(1 for value in goals.values() if isinstance(value, dict))
        required = min(int(pending_floor_u64), int(total_goals))
        gate_a_pairs.append(
            {
                "tick_u64": int(row.get("tick_u64", 0)),
                "pending_u64": int(pending),
                "done_u64": int(done),
                "required_u64": int(required),
                "total_goals_u64": int(total_goals),
            }
        )
    gate_a_pass = bool(gate_a_pairs) and all(
        int(pair["pending_u64"]) >= int(pair["required_u64"])
        or int(pair["pending_u64"] + pair["done_u64"]) >= int(pair["required_u64"])
        for pair in gate_a_pairs
    )
    gate_a_min_pending = min((int(pair["pending_u64"]) for pair in gate_a_pairs), default=0)
    gate_a_min_available = min((int(pair["pending_u64"] + pair["done_u64"]) for pair in gate_a_pairs), default=0)
    gate_a_min_required = min((int(pair["required_u64"]) for pair in gate_a_pairs), default=0)

    polymath_stats = _polymath_gate_stats(runs_root=runs_root, errors=errors)
    gate_p_pass = bool(polymath_stats.get("gate_p_pass", False))
    gate_q_pass = bool(polymath_stats.get("gate_q_pass", False))

    details = {
        "latest_tick_dir": latest_run_dir.as_posix(),
        "latest_tick_dir_id_u64": int(latest_tick_id),
        "pending_floor_u64": int(pending_floor_u64),
        "gate_a_pairs_u64": int(len(gate_a_pairs)),
        "gate_a_min_pending": int(gate_a_min_pending),
        "gate_a_min_available": int(gate_a_min_available),
        "gate_a_min_required": int(gate_a_min_required),
        "polymath_stats": dict(polymath_stats),
        "errors": sorted(set(errors)),
    }

    return {
        "schema_version": "OMEGA_BENCHMARK_GATES_v1",
        "runs_root": runs_root.as_posix(),
        "gates": {
            "A": {
                "status": "PASS" if gate_a_pass else "FAIL",
                "details": {
                    "gate_a_min_pending": int(gate_a_min_pending),
                    "gate_a_min_available": int(gate_a_min_available),
                    "gate_a_min_required": int(gate_a_min_required),
                    "gate_a_pairs_u64": int(len(gate_a_pairs)),
                },
            },
            "P": {
                "status": "PASS" if gate_p_pass else "FAIL",
                "details": {
                    "scout_dispatch_u64": int(polymath_stats.get("scout_dispatch_u64", 0)),
                    "void_hash_history_u64": int(polymath_stats.get("void_hash_history_u64", 0)),
                },
            },
            "Q": {
                "status": "PASS" if gate_q_pass else "FAIL",
                "details": {
                    "domains_bootstrapped_delta_u64": int(polymath_stats.get("domains_bootstrapped_delta_u64", 0)),
                    "conquer_improved_u64": int(polymath_stats.get("conquer_improved_u64", 0)),
                    "bootstrapped_reports_u64": int(polymath_stats.get("bootstrapped_reports_u64", 0)),
                },
            },
        },
        "details": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit OMEGA_BENCHMARK_GATES_v1.json from v19 run artifacts")
    parser.add_argument("--runs_root", default="runs/v19_full_loop", help="Root directory containing per-tick run dirs")
    parser.add_argument("--pending_floor_u64", type=int, default=_PENDING_FLOOR_U64_DEFAULT, help="Gate A required pending floor")
    args = parser.parse_args()

    runs_root = Path(str(args.runs_root)).expanduser().resolve()
    payload = build_gate_payload(runs_root=runs_root, pending_floor_u64=int(args.pending_floor_u64))

    out_path = runs_root / "OMEGA_BENCHMARK_GATES_v1.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
