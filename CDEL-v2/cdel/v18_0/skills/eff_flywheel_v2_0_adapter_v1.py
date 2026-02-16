"""Legacy efficiency/flywheel adapter (v2.0 lineage) for Omega v18."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..omega_common_v1 import rat_q32, validate_schema
from ..omega_common_v1 import load_canon_dict


def _scorecards(state_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted((state_root / "perf").glob("sha256_*.omega_run_scorecard_v1.json"), key=lambda row: row.as_posix()):
        payload = load_canon_dict(path)
        validate_schema(payload, "omega_run_scorecard_v1")
        rows.append(payload)
    return rows


def compute_skill_report(*, tick_u64: int, state_root: Path, config_dir: Path) -> dict[str, Any]:
    _ = config_dir

    flags: list[str] = []
    rows = _scorecards(state_root)
    if not rows:
        flags.append("SCORECARD_MISSING")

    promotion_success_u64 = 0
    total_ns_u64 = 0
    for row in rows[-16:]:
        promotion_success_u64 += max(0, int(row.get("promotion_success_u64", 0)))
        total_ns_u64 += max(0, int(row.get("total_ns_u64", 0)))

    total_ms_u64 = max(1, total_ns_u64 // 1_000_000)
    flywheel_yield_q32 = rat_q32(promotion_success_u64, total_ms_u64) if rows else 0

    retention_q32 = 0
    if len(rows) >= 2:
        prev_q32 = max(0, int(rows[-2].get("median_stps_non_noop_q32", 0)))
        curr_q32 = max(0, int(rows[-1].get("median_stps_non_noop_q32", 0)))
        retention_q32 = rat_q32(min(curr_q32, prev_q32), max(1, prev_q32))
        if curr_q32 < prev_q32:
            flags.append("RETENTION_REGRESSION")
    elif rows:
        retention_q32 = int(rows[-1].get("median_stps_non_noop_q32", 0))

    return {
        "schema_version": "omega_skill_report_v1",
        "skill_id": "EFF_FLYWHEEL_V2_0",
        "tick_u64": int(tick_u64),
        "metrics": {
            "flywheel_yield_q32": {"q": int(flywheel_yield_q32)},
            "flywheel_retention_q32": {"q": int(retention_q32)},
        },
        "flags": flags,
        "recommendations": [
            {
                "kind": "FLYWHEEL_TUNE",
                "detail": "Favor candidates that improve retained scorecard STPS across windows.",
            }
        ],
    }
