#!/usr/bin/env python3
"""Scan run artifacts for axis-bundle and gate-failure coverage."""

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


def _is_promotion_dir(path: Path) -> bool:
    return path.name == "promotion"


def _find_artifact_path(start_dir: Path, artifact_relpath: str) -> Path | None:
    rel = Path(str(artifact_relpath))
    for root in [start_dir, *start_dir.parents]:
        candidate = (root / rel).resolve()
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _morphism_types_from_axis_bundle(axis_path: Path) -> list[str]:
    payload = load_canon_json(axis_path)
    morphisms = payload.get("morphisms")
    if not isinstance(morphisms, list):
        return []
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
        artifact_path = _find_artifact_path(axis_path.parent, artifact_relpath)
        if artifact_path is None:
            continue
        morphism_payload = load_canon_json(artifact_path)
        morphism_type = str(morphism_payload.get("morphism_type", "")).strip()
        if morphism_type:
            out.append(morphism_type)
    return out


def scan_axis_bundle_coverage(*, roots: list[Path]) -> dict[str, Any]:
    promotion_dirs: set[str] = set()
    promotion_dirs_with_axis: set[str] = set()
    gate_failure_counts = {"SAFE_HALT": 0, "SAFE_SPLIT": 0, "OTHER": 0}
    per_morphism: dict[str, int] = {}

    axis_paths: list[Path] = []
    gate_paths: list[Path] = []

    for root in roots:
        if not root.exists():
            continue
        axis_paths.extend(sorted(root.rglob("axis_upgrade_bundle_v1.json"), key=lambda row: row.as_posix()))
        gate_paths.extend(sorted(root.rglob("axis_gate_failure_v1.json"), key=lambda row: row.as_posix()))
        for promotion_bundle in sorted(root.rglob("*promotion_bundle*.json"), key=lambda row: row.as_posix()):
            parent = promotion_bundle.parent
            if _is_promotion_dir(parent):
                promotion_dirs.add(parent.resolve().as_posix())

    for axis_path in axis_paths:
        if "meta_core_promotion_bundle_v1" in axis_path.parts:
            continue
        promotion_dir = axis_path.parent
        if not _is_promotion_dir(promotion_dir):
            continue
        key = promotion_dir.resolve().as_posix()
        promotion_dirs_with_axis.add(key)
        promotion_dirs.add(key)
        for morphism_type in _morphism_types_from_axis_bundle(axis_path):
            per_morphism[morphism_type] = int(per_morphism.get(morphism_type, 0)) + 1

    for gate_path in gate_paths:
        if "meta_core_promotion_bundle_v1" in gate_path.parts:
            continue
        parent = gate_path.parent
        if _is_promotion_dir(parent):
            promotion_dirs.add(parent.resolve().as_posix())
        payload = load_canon_json(gate_path)
        outcome = str(payload.get("outcome", "")).strip()
        if outcome == "SAFE_HALT":
            gate_failure_counts["SAFE_HALT"] += 1
        elif outcome == "SAFE_SPLIT":
            gate_failure_counts["SAFE_SPLIT"] += 1
        else:
            gate_failure_counts["OTHER"] += 1

    return {
        "schema_name": "v19_axis_bundle_coverage_scan_v1",
        "schema_version": "v19_0",
        "roots": [str(root.resolve()) for root in roots],
        "total_promotions_detected": len(promotion_dirs),
        "promotions_with_axis_upgrade_bundle": len(promotion_dirs_with_axis),
        "axis_bundle_coverage_ratio": {
            "num_u64": len(promotion_dirs_with_axis),
            "den_u64": max(1, len(promotion_dirs)),
        },
        "axis_gate_failures": gate_failure_counts,
        "per_morphism_frequency": {key: int(per_morphism[key]) for key in sorted(per_morphism.keys())},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan run dirs for axis-bundle usage coverage")
    parser.add_argument(
        "--root",
        action="append",
        default=None,
        help="Root directory to scan (repeatable)",
    )
    parser.add_argument(
        "--out",
        default="runs/v19_axis_bundle_coverage_scan.json",
        help="Output JSON path for coverage report",
    )
    args = parser.parse_args()

    raw_roots = list(args.root) if isinstance(args.root, list) and args.root else ["runs"]
    roots = [Path(str(row)).resolve() for row in raw_roots]
    summary = scan_axis_bundle_coverage(roots=roots)
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
