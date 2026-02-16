#!/usr/bin/env python3
"""Compute a single "level attainment" report from v19 run artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
_ORDERED_PATHS = [str(REPO_ROOT / "CDEL-v2"), str(REPO_ROOT)]
for _path in _ORDERED_PATHS:
    while _path in sys.path:
        sys.path.remove(_path)
for _path in reversed(_ORDERED_PATHS):
    sys.path.insert(0, _path)

from cdel.v1_7r.canon import load_canon_json


LEVELS: tuple[tuple[str, str], ...] = (
    ("L0", "M_SIGMA"),
    ("L1", "M_SIGMA"),
    ("L2", "M_PI"),
    ("L3", "M_D"),
    ("L4", "M_H"),
    ("L5", "M_A"),
    ("L6", "M_K"),
    ("L7", "M_E"),
    ("L8", "M_M"),
    ("L9", "M_C"),
    ("L10", "M_W"),
    ("L11", "M_T"),
)


def _load_dict(path: Path) -> dict[str, Any]:
    payload = load_canon_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _morphism_types_from_axis_bundle(axis_path: Path) -> list[str]:
    axis = _load_dict(axis_path)
    morphisms = axis.get("morphisms")
    if not isinstance(morphisms, list):
        return []
    # axis bundle lives at .../meta_core_promotion_bundle_v1/omega/axis_upgrade_bundle_v1.json
    bundle_root = axis_path.parent.parent
    out: list[str] = []
    for row in morphisms:
        if not isinstance(row, dict):
            continue
        morphism_ref = row.get("morphism_ref")
        if not isinstance(morphism_ref, dict):
            continue
        artifact_relpath = str(morphism_ref.get("artifact_relpath", "")).strip()
        if not artifact_relpath:
            continue
        artifact_path = (bundle_root / artifact_relpath).resolve()
        if not artifact_path.exists() or not artifact_path.is_file():
            continue
        morphism = _load_dict(artifact_path)
        morphism_type = str(morphism.get("morphism_type", "")).strip()
        if morphism_type:
            out.append(morphism_type)
    return out


def _max_level_achieved(morphism_types_promoted: set[str]) -> tuple[str | None, list[str]]:
    achieved: list[str] = []
    max_level: str | None = None
    for idx, (level, _required) in enumerate(LEVELS):
        required_prefix = {m for _lvl, m in LEVELS[: idx + 1]}
        if required_prefix.issubset(morphism_types_promoted):
            achieved.append(level)
            max_level = level
    return max_level, achieved


def build_report(*, runs_root: Path) -> dict[str, Any]:
    runs_root = runs_root.resolve()

    promotion_receipt_paths = sorted(
        runs_root.rglob("sha256_*.omega_promotion_receipt_v1.json"),
        key=lambda row: row.as_posix(),
    )
    total_receipts = 0
    promoted_receipts = 0
    receipts_with_axis_bundle = 0

    per_morphism: dict[str, int] = {}
    morphism_types_promoted: set[str] = set()

    for receipt_path in promotion_receipt_paths:
        receipt = _load_dict(receipt_path)
        total_receipts += 1
        status = str((receipt.get("result") or {}).get("status", "")).strip()
        if status == "PROMOTED":
            promoted_receipts += 1

        axis_path = receipt_path.parent / "meta_core_promotion_bundle_v1" / "omega" / "axis_upgrade_bundle_v1.json"
        if axis_path.exists() and axis_path.is_file():
            receipts_with_axis_bundle += 1
        else:
            continue

        if status != "PROMOTED":
            continue

        for morphism_type in _morphism_types_from_axis_bundle(axis_path):
            per_morphism[morphism_type] = int(per_morphism.get(morphism_type, 0)) + 1
            morphism_types_promoted.add(morphism_type)

    gate_failure_counts: dict[str, int] = {}
    for gate_path in sorted(runs_root.rglob("axis_gate_failure_v1.json"), key=lambda row: row.as_posix()):
        payload = _load_dict(gate_path)
        outcome = str(payload.get("outcome", "")).strip() or "UNKNOWN"
        gate_failure_counts[outcome] = int(gate_failure_counts.get(outcome, 0)) + 1

    max_level, achieved_levels = _max_level_achieved(morphism_types_promoted)

    return {
        "schema_name": "v19_level_attainment_report_v1",
        "schema_version": "v19_0",
        "runs_root": str(runs_root),
        "promotions": {
            "receipts_total_u64": total_receipts,
            "receipts_promoted_u64": promoted_receipts,
            "receipts_with_axis_upgrade_bundle_u64": receipts_with_axis_bundle,
        },
        "axis_gate_failures_by_outcome_u64": {k: int(gate_failure_counts[k]) for k in sorted(gate_failure_counts.keys())},
        "morphism_histogram_promoted_u64": {k: int(per_morphism[k]) for k in sorted(per_morphism.keys())},
        "morphism_types_promoted": sorted(morphism_types_promoted),
        "levels": {
            "mapping": [{"level": lvl, "morphism_type": m} for lvl, m in LEVELS],
            "achieved_levels_monotone": achieved_levels,
            "max_level_achieved": max_level,
        },
    }


def _render_md(report: dict[str, Any]) -> str:
    promotions = report.get("promotions") if isinstance(report.get("promotions"), dict) else {}
    gate_failures = report.get("axis_gate_failures_by_outcome_u64") if isinstance(report.get("axis_gate_failures_by_outcome_u64"), dict) else {}
    histogram = report.get("morphism_histogram_promoted_u64") if isinstance(report.get("morphism_histogram_promoted_u64"), dict) else {}
    levels = report.get("levels") if isinstance(report.get("levels"), dict) else {}

    lines: list[str] = []
    lines.append("# V19 Level Attainment Report v1")
    lines.append("")
    lines.append(f"- runs_root: `{report.get('runs_root', '')}`")
    lines.append(f"- promotion receipts total: `{promotions.get('receipts_total_u64', 0)}`")
    lines.append(f"- promotion receipts promoted: `{promotions.get('receipts_promoted_u64', 0)}`")
    lines.append(f"- receipts with axis bundle: `{promotions.get('receipts_with_axis_upgrade_bundle_u64', 0)}`")
    lines.append(f"- max level achieved: `{levels.get('max_level_achieved')}`")
    achieved = levels.get("achieved_levels_monotone") if isinstance(levels.get("achieved_levels_monotone"), list) else []
    lines.append(f"- achieved levels (monotone): `{','.join(str(x) for x in achieved)}`")
    lines.append("")
    lines.append("## Axis Gate Failures")
    if gate_failures:
        for key in sorted(gate_failures.keys()):
            lines.append(f"- {key}: {int(gate_failures[key])}")
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("## Morphism Histogram (PROMOTED)")
    if histogram:
        for key in sorted(histogram.keys()):
            lines.append(f"- {key}: {int(histogram[key])}")
    else:
        lines.append("- (none)")
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute v19 level attainment report from run artifacts")
    parser.add_argument("--runs_root", default="runs/v19_full_loop", help="Root directory containing per-tick run dirs")
    args = parser.parse_args()

    runs_root = Path(str(args.runs_root)).expanduser().resolve()
    report = build_report(runs_root=runs_root)

    json_path = runs_root / "V19_LEVEL_ATTAINMENT_REPORT_v1.json"
    md_path = runs_root / "V19_LEVEL_ATTAINMENT_REPORT_v1.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
