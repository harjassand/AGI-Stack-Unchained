#!/usr/bin/env python3
"""Load benchmark gate statuses with JSON-first fallback semantics."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_GATE_STATUS_RE = re.compile(r"- Gate ([A-Z]).*\*\*(PASS|FAIL|SKIP)\*\*")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_gate_statuses_from_json(path: Path) -> dict[str, str]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        payload = _load_json(path)
    except Exception:  # noqa: BLE001
        return {}
    gates = payload.get("gates")
    if not isinstance(gates, dict):
        return {}
    out: dict[str, str] = {}
    for gate, row in gates.items():
        gate_id = str(gate).strip()
        if not gate_id:
            continue
        if not isinstance(row, dict):
            continue
        status = str(row.get("status", "")).strip()
        if status:
            out[gate_id] = status
    return out


def _load_gate_statuses_from_md(path: Path) -> dict[str, str]:
    if not path.exists() or not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _GATE_STATUS_RE.search(line)
        if not match:
            continue
        out[str(match.group(1))] = str(match.group(2))
    return out


def load_gate_statuses(run_dir: Path) -> dict[str, str]:
    """
    Returns { "A": "PASS"|"FAIL"|"SKIP", ... }.
    Prefer OMEGA_BENCHMARK_GATES_v1.json; fallback to parsing OMEGA_BENCHMARK_SUMMARY_v1.md.
    """

    run_path = run_dir.resolve()
    json_status = _load_gate_statuses_from_json(run_path / "OMEGA_BENCHMARK_GATES_v1.json")
    if json_status:
        return json_status
    return _load_gate_statuses_from_md(run_path / "OMEGA_BENCHMARK_SUMMARY_v1.md")


__all__ = ["load_gate_statuses"]
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=0
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=1
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=2
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=3
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=4
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=5
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=6
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=7
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=8
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=9
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=10
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=11
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=12
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=13
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=14
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=15
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=16
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=17
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=18
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=19
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=20
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=21
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=22
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=23
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=24
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=25
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=26
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=27
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=28
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=29
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=30
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=31
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=32
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=33
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=34
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=35
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=36
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=37
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=38
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=39
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=40
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=41
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=42
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=43
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=44
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=45
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=46
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=47
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=48
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=49
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=50
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=51
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=52
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=53
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=54
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=55
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=56
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=57
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=58
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=59
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=60
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=61
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=62
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=63
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=64
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=65
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=66
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=67
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=68
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=69
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=70
# SIDC_HEAVY_DIFF tick=4 ordinal=1 agent=micdrop_template_v1 file=tools/omega/omega_gate_loader_v1.py file_idx=5 line_idx=71
