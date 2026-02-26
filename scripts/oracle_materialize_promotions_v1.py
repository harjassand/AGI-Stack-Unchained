#!/usr/bin/env python3
"""Materialize accepted oracle promotions into the mutable synthesizer."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MARKER_RE = re.compile(r"^# ORACLE_SYNTH_CAPABILITY_LEVEL:(\d+)\s*$", re.MULTILINE)
_CONST_RE = re.compile(r"^ORACLE_SYNTH_CAPABILITY_LEVEL\s*=\s*(\d+)\s*$", re.MULTILINE)


def _load_promotions(ticks_dir: Path) -> list[dict[str, Any]]:
    plan_path = ticks_dir / "promotion_plan_v1.json"
    if not plan_path.exists() or not plan_path.is_file():
        return []
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return []
    rows = payload.get("accepted_promotions")
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            out.append(dict(row))
    return out


def _read_level(content: str) -> int:
    marker_match = _MARKER_RE.search(content)
    const_match = _CONST_RE.search(content)
    if marker_match is None or const_match is None:
        raise RuntimeError("synthesizer capability markers are missing")
    marker_level = int(marker_match.group(1))
    const_level = int(const_match.group(1))
    if marker_level != const_level:
        raise RuntimeError("synthesizer capability marker mismatch")
    return int(marker_level)


def _rewrite_level(content: str, target_level: int) -> str:
    next_text, marker_count = _MARKER_RE.subn(f"# ORACLE_SYNTH_CAPABILITY_LEVEL:{int(target_level)}", content, count=1)
    if marker_count != 1:
        raise RuntimeError("failed to rewrite synthesizer marker comment")
    next_text, const_count = _CONST_RE.subn(f"ORACLE_SYNTH_CAPABILITY_LEVEL = {int(target_level)}", next_text, count=1)
    if const_count != 1:
        raise RuntimeError("failed to rewrite synthesizer marker constant")
    return next_text


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="oracle_materialize_promotions_v1")
    parser.add_argument("--ticks_dir", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--synthesizer_path", default="tools/omega/oracle_synthesizer_v1.py")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    ticks_dir = Path(str(args.ticks_dir)).resolve()
    out_path = Path(str(args.out)).resolve()
    synth_path = (_REPO_ROOT / str(args.synthesizer_path)).resolve()
    if not synth_path.exists() or not synth_path.is_file():
        raise RuntimeError("synthesizer file missing")

    content = synth_path.read_text(encoding="utf-8")
    prior_level = _read_level(content)
    promotions = _load_promotions(ticks_dir)
    accepted = [row for row in promotions if bool(row.get("accepted_b", True))]
    activated = [row for row in accepted if bool(row.get("activation_success_b", True))]

    target_level = int(prior_level)
    for row in activated:
        row_level = int(row.get("target_capability_level", prior_level))
        if row_level > target_level:
            target_level = row_level

    materialized_b = False
    if target_level != prior_level:
        synth_path.write_text(_rewrite_level(content, target_level), encoding="utf-8")
        materialized_b = True

    summary = {
        "schema_version": "oracle_materialize_promotions_v1",
        "synthesizer_path": synth_path.relative_to(_REPO_ROOT).as_posix(),
        "prior_capability_level": int(prior_level),
        "final_capability_level": int(target_level),
        "accepted_promotions_u64": int(len(accepted)),
        "activation_success_u64": int(len(activated)),
        "materialized_b": bool(materialized_b),
        "applied_promotions": [
            {
                "promotion_id": str(row.get("promotion_id", "")),
                "target_capability_level": int(row.get("target_capability_level", prior_level)),
                "activation_success_b": bool(row.get("activation_success_b", True)),
                "touched_paths": list(row.get("touched_paths") or ["tools/omega/oracle_synthesizer_v1.py"]),
            }
            for row in activated
        ],
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
