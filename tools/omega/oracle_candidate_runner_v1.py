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
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=0
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=1
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=2
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=3
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=4
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=5
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=6
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=7
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=8
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=9
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=10
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=11
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=12
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=13
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=14
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=15
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=16
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=17
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=18
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=19
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=20
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=21
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=22
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=23
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=24
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=25
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=26
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=27
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=28
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=29
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=30
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=31
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=32
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=33
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=34
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=35
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=36
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=37
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=38
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=39
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=40
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=41
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=42
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=43
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=44
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=45
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=46
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=47
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=48
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=49
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=50
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=51
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=52
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=53
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=54
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=55
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=56
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=57
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=58
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=59
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=60
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=61
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=62
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=63
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=64
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=65
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=66
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=67
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=68
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=69
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=70
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/oracle_candidate_runner_v1.py file_idx=2 line_idx=71
