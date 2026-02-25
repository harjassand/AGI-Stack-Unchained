#!/usr/bin/env python3
"""Simulate bounded autonomy ticks for micdrop by emitting promotion intents."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    _value = str(_entry)
    if _value not in sys.path:
        sys.path.insert(0, _value)

from cdel.v1_7r.canon import write_canon_json
_MARKER_RE = re.compile(r"^# MICDROP_CAPABILITY_LEVEL:(\d+)\s*$", re.MULTILINE)


def _read_level(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    match = _MARKER_RE.search(text)
    if match is None:
        raise RuntimeError("solver capability marker missing")
    return int(match.group(1))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="micdrop_simulate_ticks_v1")
    parser.add_argument("--ticks_dir", required=True)
    parser.add_argument("--ticks", type=int, default=30)
    parser.add_argument("--target_level", type=int, default=4)
    parser.add_argument("--seed_u64", type=int, required=True)
    parser.add_argument("--solver_path", default="tools/omega/agi_micdrop_solver_v1.py")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    ticks_dir = Path(str(args.ticks_dir)).resolve()
    ticks_dir.mkdir(parents=True, exist_ok=True)
    solver_path = (_REPO_ROOT / str(args.solver_path)).resolve()
    from_level = _read_level(solver_path)
    target_level = max(int(from_level), int(args.target_level))
    ticks = max(1, int(args.ticks))

    promotions = []
    levels = list(range(int(from_level) + 1, int(target_level) + 1))
    for idx, level in enumerate(levels):
        tick_u64 = min(ticks, 1 + idx)
        promotions.append(
            {
                "promotion_id": f"seed_{int(args.seed_u64)}_lvl_{int(level)}",
                "tick_u64": int(tick_u64),
                "accepted_b": True,
                "activation_success_b": True,
                "target_capability_level": int(level),
                "file": "tools/omega/agi_micdrop_solver_v1.py",
            }
        )

    payload = {
        "schema_version": "micdrop_tick_promotions_v1",
        "seed_u64": int(args.seed_u64),
        "ticks_u64": int(ticks),
        "start_capability_level": int(from_level),
        "target_capability_level": int(target_level),
        "accepted_promotions": promotions,
    }
    out_path = ticks_dir / "promotion_plan_v1.json"
    write_canon_json(out_path, payload)
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
