"""Legacy thermodynamic adapter (v5 lineage) for Omega v18."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..omega_common_v1 import Q32_ONE, rat_q32, validate_schema
from ..omega_common_v1 import load_canon_dict


def _latest_scorecard(state_root: Path) -> dict[str, Any] | None:
    rows = sorted((state_root / "perf").glob("sha256_*.omega_run_scorecard_v1.json"), key=lambda row: row.as_posix())
    if not rows:
        return None
    payload = load_canon_dict(rows[-1])
    validate_schema(payload, "omega_run_scorecard_v1")
    return payload


def compute_skill_report(*, tick_u64: int, state_root: Path, config_dir: Path) -> dict[str, Any]:
    _ = config_dir

    flags: list[str] = []
    scorecard = _latest_scorecard(state_root)
    if scorecard is None:
        flags.append("SCORECARD_MISSING")
        return {
            "schema_version": "omega_skill_report_v1",
            "skill_id": "THERMO_V5",
            "tick_u64": int(tick_u64),
            "metrics": {
                "thermo_efficiency_q32": {"q": 0},
                "thermo_dissipation_q32": {"q": 0},
            },
            "flags": flags,
            "recommendations": [
                {
                    "kind": "THERMO_REVIEW",
                    "detail": "Collect scorecards before applying thermo optimization policy.",
                }
            ],
        }

    total_ns_u64 = max(1, int(scorecard.get("total_ns_u64", 0)))
    total_ms_u64 = max(1, total_ns_u64 // 1_000_000)
    utility_q32 = max(0, int(scorecard.get("median_stps_non_noop_q32", 0)))

    overhead_ns_u64 = (
        max(0, int(scorecard.get("avg_dispatch_ns_u64", 0)))
        + max(0, int(scorecard.get("avg_subverifier_ns_u64", 0)))
        + max(0, int(scorecard.get("avg_promotion_ns_u64", 0)))
    )

    thermo_efficiency_q32 = rat_q32(utility_q32, total_ms_u64)
    thermo_dissipation_q32 = rat_q32(overhead_ns_u64, total_ns_u64)
    if thermo_dissipation_q32 >= (Q32_ONE // 2):
        flags.append("THERMO_DISSIPATION_HIGH")

    return {
        "schema_version": "omega_skill_report_v1",
        "skill_id": "THERMO_V5",
        "tick_u64": int(tick_u64),
        "metrics": {
            "thermo_efficiency_q32": {"q": int(thermo_efficiency_q32)},
            "thermo_dissipation_q32": {"q": int(thermo_dissipation_q32)},
        },
        "flags": flags,
        "recommendations": [
            {
                "kind": "THERMO_REVIEW",
                "detail": "Prioritize lower overhead stages when dissipation remains high.",
            }
        ],
    }
