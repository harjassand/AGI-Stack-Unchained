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
