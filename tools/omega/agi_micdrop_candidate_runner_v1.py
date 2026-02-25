#!/usr/bin/env python3
"""Micdrop holdout candidate runner v1."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from tools.omega.agi_micdrop_solver_v1 import solve


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="agi_micdrop_candidate_runner_v1")
    parser.add_argument("--mode", required=True)
    parser.add_argument("--inputs_pack_path", required=True)
    parser.add_argument("--out_dir", required=True)
    parser.add_argument("--suite_id", required=True)
    parser.add_argument("--ticks")
    parser.add_argument("--seed_u64")
    return parser.parse_args()


def _load_inputs(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("inputs pack must be an object")
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError("inputs pack rows must be an array")
    out: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            out.append(dict(row))
    return out


def _write_predictions(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for row in rows:
        row_id = str(row.get("id", "")).strip()
        if not row_id:
            continue
        prompt = str(row.get("prompt", ""))
        meta = row.get("meta")
        meta_obj = dict(meta) if isinstance(meta, dict) else {}
        prediction = solve(prompt, meta=meta_obj)
        line_obj = {"id": row_id, "prediction": str(prediction)}
        lines.append(json.dumps(line_obj, sort_keys=True, separators=(",", ":")))
    path.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")


def main() -> int:
    args = _parse_args()
    if str(args.mode).strip() != "holdout_candidate":
        return 2

    rows = _load_inputs(Path(str(args.inputs_pack_path)))
    out_dir = Path(str(args.out_dir)).resolve()
    _write_predictions(out_dir / "predictions.jsonl", rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
