#!/usr/bin/env python3
"""Holdout candidate runner for oracle ladder tasks."""

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

from tools.omega.oracle_synthesizer_v1 import synthesize


def _load_inputs_pack(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("inputs pack must be a JSON object")
    if str(payload.get("schema_version", "")).strip() != "oracle_task_inputs_pack_v1":
        raise RuntimeError("inputs pack schema mismatch")
    tasks = payload.get("tasks")
    if not isinstance(tasks, list):
        raise RuntimeError("inputs pack tasks missing")
    out: list[dict[str, Any]] = []
    for task in tasks:
        if not isinstance(task, dict):
            raise RuntimeError("task must be object")
        task_id = str(task.get("id", "")).strip()
        if not task_id:
            raise RuntimeError("task id missing")
        out.append(dict(task))
    return out


def _write_predictions(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")


def _run_holdout_candidate(*, inputs_pack_path: Path, out_dir: Path, ticks: int, seed_u64: int) -> int:
    tasks = _load_inputs_pack(inputs_pack_path)
    predictions: list[dict[str, Any]] = []
    for idx, task in enumerate(tasks):
        task_id = str(task.get("id", "")).strip()
        task_seed = (int(seed_u64) + int(idx) * 0x9E3779B97F4A7C15) & ((1 << 64) - 1)
        ast_obj = synthesize(task, seed_u64=task_seed, ticks_budget_u64=max(1, int(ticks)))
        ast_text = json.dumps(ast_obj, sort_keys=True, separators=(",", ":"))
        predictions.append({"id": task_id, "prediction": ast_text})
    _write_predictions(out_dir / "predictions.jsonl", predictions)
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="oracle_candidate_runner_v1")
    parser.add_argument("--mode", default="holdout_candidate")
    parser.add_argument("--inputs_pack_path", required=True)
    parser.add_argument("--out_dir", required=True)
    parser.add_argument("--suite_id", default="")
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
        _run_holdout_candidate(
            inputs_pack_path=inputs_pack_path,
            out_dir=out_dir,
            ticks=max(1, int(args.ticks)),
            seed_u64=max(0, int(args.seed_u64)),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"INVALID:{str(exc) or 'candidate runner failed'}")
        return 1

    print("VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
