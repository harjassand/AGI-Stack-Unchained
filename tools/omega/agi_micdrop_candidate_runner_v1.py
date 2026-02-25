#!/usr/bin/env python3
"""Holdout candidate runner for micdrop tasks."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.omega.agi_micdrop_solver_v1 import solve_prompt


def _load_inputs_pack(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("inputs pack must be a JSON object")
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise RuntimeError("inputs pack rows missing")
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise RuntimeError("input row must be an object")
        row_id = str(row.get("id", "")).strip()
        prompt = str(row.get("prompt", "")).strip()
        if not row_id or not prompt:
            raise RuntimeError("input row missing id/prompt")
        meta = row.get("meta")
        out.append({"id": row_id, "prompt": prompt, "meta": meta if isinstance(meta, dict) else {}})
    return out


def _write_predictions(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")


def _run_holdout_candidate(*, inputs_pack_path: Path, out_dir: Path) -> int:
    inputs = _load_inputs_pack(inputs_pack_path)
    predictions: list[dict[str, Any]] = []
    for row in inputs:
        pred = solve_prompt(str(row["prompt"]), row.get("meta") if isinstance(row.get("meta"), dict) else None)
        predictions.append({"id": str(row["id"]), "prediction": str(pred)})
    _write_predictions(out_dir / "predictions.jsonl", predictions)
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="agi_micdrop_candidate_runner_v1")
    parser.add_argument("--mode", default="holdout_candidate")
    parser.add_argument("--suite_id", default="")
    parser.add_argument("--inputs_pack_path", required=True)
    parser.add_argument("--out_dir", required=True)
    parser.add_argument("--ticks", type=int, default=1)
    parser.add_argument("--seed_u64", type=int, default=0)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    mode = str(args.mode).strip()
    if mode != "holdout_candidate":
        print("INVALID:MODE_UNSUPPORTED")
        return 1

    inputs_pack_path = Path(str(args.inputs_pack_path)).resolve()
    out_dir = Path(str(args.out_dir)).resolve()
    if not inputs_pack_path.exists() or not inputs_pack_path.is_file():
        print("INVALID:MISSING_INPUTS_PACK")
        return 1

    os.environ.setdefault("PYTHONHASHSEED", "0")
    try:
        _run_holdout_candidate(inputs_pack_path=inputs_pack_path, out_dir=out_dir)
    except Exception as exc:  # noqa: BLE001
        print(f"INVALID:{str(exc) or 'candidate runner failed'}")
        return 1
    print("VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
