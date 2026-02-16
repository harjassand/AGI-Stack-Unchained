"""Generic legacy skill runner for Omega v18."""

from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import Any

from ...v1_7r.canon import write_canon_json
from ..omega_common_v1 import (
    Q32_ONE,
    canon_hash_obj,
    load_canon_dict,
    repo_root,
    validate_schema,
    write_hashed_json,
)

_SHA256_ZERO = "sha256:" + ("0" * 64)


def _latest_hashed_payload_hash(*, path: Path, suffix: str, schema_name: str | None = None) -> tuple[str, dict[str, Any] | None]:
    rows = sorted(path.glob(f"sha256_*.{suffix}"), key=lambda row: row.as_posix())
    if not rows:
        return _SHA256_ZERO, None
    payload = load_canon_dict(rows[-1])
    if schema_name is not None:
        validate_schema(payload, schema_name)
    return canon_hash_obj(payload), payload


def _state_rel_for_descriptor(state_root: Path) -> str:
    try:
        return state_root.resolve().relative_to(repo_root().resolve()).as_posix()
    except Exception:  # noqa: BLE001
        return state_root.name


def discover_authoritative_state_root(preferred_state_root: Path | None = None) -> Path | None:
    if preferred_state_root is not None:
        resolved = preferred_state_root.resolve()
        if resolved.exists() and resolved.is_dir():
            return resolved

    env_rel = str(os.environ.get("OMEGA_DAEMON_STATE_ROOT_REL", "")).strip()
    if env_rel:
        candidate = (repo_root() / env_rel).resolve()
        if candidate.exists() and candidate.is_dir():
            return candidate

    env_abs = str(os.environ.get("OMEGA_DAEMON_STATE_ROOT", "")).strip()
    if env_abs:
        candidate = Path(env_abs).expanduser().resolve()
        if candidate.exists() and candidate.is_dir():
            return candidate

    direct_candidate = (repo_root() / "daemon" / "rsi_omega_daemon_v18_0" / "state").resolve()
    best_state: Path | None = direct_candidate if direct_candidate.exists() and direct_candidate.is_dir() else None
    best_tick = -1

    runs_root = repo_root() / "runs"
    if runs_root.exists() and runs_root.is_dir():
        rows = sorted(
            runs_root.glob("*/daemon/rsi_omega_daemon_v18_0/state/snapshot/sha256_*.omega_tick_snapshot_v1.json"),
            key=lambda row: row.as_posix(),
        )
        for snapshot_path in rows:
            try:
                snapshot = load_canon_dict(snapshot_path)
                validate_schema(snapshot, "omega_tick_snapshot_v1")
                tick_u64 = int(snapshot.get("tick_u64", -1))
            except Exception:  # noqa: BLE001
                continue
            state_root = snapshot_path.parent.parent.resolve()
            if not state_root.exists() or not state_root.is_dir():
                continue
            if tick_u64 > best_tick or (tick_u64 == best_tick and state_root.as_posix() > (best_state or Path()).as_posix()):
                best_tick = tick_u64
                best_state = state_root

    return best_state


def _inputs_descriptor(*, state_root: Path, config_dir: Path) -> dict[str, Any]:
    snapshot_hash, _snapshot_payload = _latest_hashed_payload_hash(
        path=state_root / "snapshot",
        suffix="omega_tick_snapshot_v1.json",
        schema_name="omega_tick_snapshot_v1",
    )
    observation_hash, _ = _latest_hashed_payload_hash(
        path=state_root / "observations",
        suffix="omega_observation_report_v1.json",
        schema_name="omega_observation_report_v1",
    )
    state_hash, _ = _latest_hashed_payload_hash(
        path=state_root / "state",
        suffix="omega_state_v1.json",
        schema_name="omega_state_v1",
    )
    trace_hash, _ = _latest_hashed_payload_hash(
        path=state_root / "ledger",
        suffix="omega_trace_hash_chain_v1.json",
        schema_name="omega_trace_hash_chain_v1",
    )
    perf_hash, _ = _latest_hashed_payload_hash(
        path=state_root / "perf",
        suffix="omega_tick_perf_v1.json",
        schema_name="omega_tick_perf_v1",
    )
    stats_hash, _ = _latest_hashed_payload_hash(
        path=state_root / "perf",
        suffix="omega_tick_stats_v1.json",
        schema_name="omega_tick_stats_v1",
    )
    scorecard_hash, _ = _latest_hashed_payload_hash(
        path=state_root / "perf",
        suffix="omega_run_scorecard_v1.json",
        schema_name="omega_run_scorecard_v1",
    )

    return {
        "schema_version": "omega_skill_inputs_descriptor_v1",
        "state_root_rel": _state_rel_for_descriptor(state_root),
        "config_rel": _state_rel_for_descriptor(config_dir),
        "hashes": {
            "snapshot_hash": snapshot_hash,
            "observation_hash": observation_hash,
            "state_hash": state_hash,
            "trace_hash_chain_hash": trace_hash,
            "tick_perf_hash": perf_hash,
            "tick_stats_hash": stats_hash,
            "run_scorecard_hash": scorecard_hash,
        },
    }


def _normalize_q_metrics(metrics: Any) -> dict[str, dict[str, int]]:
    if not isinstance(metrics, dict):
        raise RuntimeError("SCHEMA_FAIL")
    out: dict[str, dict[str, int]] = {}
    for key in sorted(metrics.keys()):
        row = metrics.get(key)
        if not isinstance(row, dict) or set(row.keys()) != {"q"}:
            raise RuntimeError("SCHEMA_FAIL")
        out[str(key)] = {"q": int(row.get("q", 0))}
    return out


def _normalize_flags(flags: Any) -> list[str]:
    if not isinstance(flags, list):
        raise RuntimeError("SCHEMA_FAIL")
    return [str(row) for row in flags]


def _normalize_recommendations(rows: Any) -> list[dict[str, str]]:
    if not isinstance(rows, list):
        raise RuntimeError("SCHEMA_FAIL")
    out: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise RuntimeError("SCHEMA_FAIL")
        out.append(
            {
                "kind": str(row.get("kind", "")),
                "detail": str(row.get("detail", "")),
            }
        )
    return out


def run_skill_report(
    *,
    tick_u64: int,
    state_root: Path,
    config_dir: Path,
    out_dir: Path,
    adapter_module: str,
    fixed_report_path: Path | None = None,
) -> tuple[dict[str, Any], str]:
    module = importlib.import_module(adapter_module)
    compute_fn = getattr(module, "compute_skill_report", None)
    if not callable(compute_fn):
        raise RuntimeError("SCHEMA_FAIL")

    descriptor = _inputs_descriptor(state_root=state_root, config_dir=config_dir)
    inputs_hash = canon_hash_obj(descriptor)

    payload_raw = compute_fn(
        tick_u64=int(tick_u64),
        state_root=state_root,
        config_dir=config_dir,
    )
    if not isinstance(payload_raw, dict):
        raise RuntimeError("SCHEMA_FAIL")

    payload: dict[str, Any] = {
        "schema_version": "omega_skill_report_v1",
        "skill_id": str(payload_raw.get("skill_id", "")),
        "tick_u64": int(tick_u64),
        "inputs_hash": inputs_hash,
        "metrics": _normalize_q_metrics(payload_raw.get("metrics", {})),
        "flags": _normalize_flags(payload_raw.get("flags", [])),
        "recommendations": _normalize_recommendations(payload_raw.get("recommendations", [])),
    }
    validate_schema(payload, "omega_skill_report_v1")

    reports_dir = out_dir / "reports"
    _, report_obj, report_hash = write_hashed_json(reports_dir, "omega_skill_report_v1.json", payload)
    write_canon_json(reports_dir / "omega_skill_report_v1.json", report_obj)

    if fixed_report_path is not None:
        fixed_report_path.parent.mkdir(parents=True, exist_ok=True)
        write_canon_json(fixed_report_path, report_obj)

    return report_obj, report_hash


def q32_bool(value: bool) -> dict[str, int]:
    return {"q": int(Q32_ONE if value else 0)}


__all__ = ["discover_authoritative_state_root", "q32_bool", "run_skill_report"]
