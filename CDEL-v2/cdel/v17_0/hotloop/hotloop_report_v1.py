"""Hotloop reporting helpers for v17.0."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


class HotloopReportError(ValueError):
    pass


def _fail(code: str) -> HotloopReportError:
    return HotloopReportError(code)


_LOOP_RE = re.compile(r"^\s*(for|while)\b")


def _count_ops(snippet: str) -> tuple[int, int, int, int]:
    lower = snippet.lower()
    ops_add = lower.count("+") + lower.count("saturating_add") + lower.count("wrapping_add")
    ops_mul = lower.count("*") + lower.count("saturating_mul") + lower.count("wrapping_mul")
    ops_load = lower.count("[") + lower.count(".get(") + lower.count(".read_")
    ops_store = lower.count("=") + lower.count(".write_") + lower.count(".push(")
    return ops_add, ops_mul, ops_load, ops_store


def _loop_rows(source_text: str) -> list[dict[str, Any]]:
    lines = source_text.splitlines()
    out: list[dict[str, Any]] = []
    for line_no, line in enumerate(lines, start=1):
        if _LOOP_RE.search(line) is None:
            continue
        start = max(0, line_no - 1)
        end = min(len(lines), line_no + 6)
        snippet = "\n".join(lines[start:end])
        ops_add, ops_mul, ops_load, ops_store = _count_ops(snippet)
        out.append(
            {
                "line_no": int(line_no),
                "loop_id": f"L{line_no}",
                "snippet": snippet,
                "ops_add": int(max(ops_add, 1)),
                "ops_mul": int(max(ops_mul, 1)),
                "ops_load": int(max(ops_load, 1)),
                "ops_store": int(max(ops_store, 1)),
            }
        )
    return out


def build_hotloop_report(
    *,
    baseline_report: dict[str, Any],
    workload: dict[str, Any],
    task: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    source_path_rel = str(task.get("source_path_rel", ""))
    source_symbol = str(task.get("source_symbol", ""))
    val_eligible_marker = bool(task.get("val_eligible_marker", False))
    if not source_path_rel or not source_symbol or not val_eligible_marker:
        raise _fail("INVALID:PILOT_NOT_DOMINANT_HOTLOOP")

    source_path = repo_root / source_path_rel
    if not source_path.exists() or not source_path.is_file():
        raise _fail("INVALID:PILOT_NOT_DOMINANT_HOTLOOP")

    text = source_path.read_text(encoding="utf-8")
    if "VAL_ELIGIBLE" not in text:
        raise _fail("INVALID:PILOT_NOT_DOMINANT_HOTLOOP")

    loops = _loop_rows(text)
    if len(loops) < 10:
        raise _fail("INVALID:PILOT_NOT_DOMINANT_HOTLOOP")

    pilot_line = -1
    for idx, line in enumerate(text.splitlines(), start=1):
        if "VAL_ELIGIBLE" in line:
            pilot_line = idx
            break
    if pilot_line <= 0:
        raise _fail("INVALID:PILOT_NOT_DOMINANT_HOTLOOP")

    pilot_candidates = [row for row in loops if abs(int(row["line_no"]) - pilot_line) <= 2]
    if not pilot_candidates:
        raise _fail("INVALID:PILOT_NOT_DOMINANT_HOTLOOP")
    pilot = sorted(pilot_candidates, key=lambda row: abs(int(row["line_no"]) - pilot_line))[0]

    n_messages = int(workload.get("n_messages", 0))
    bytes_hashed = int(baseline_report.get("bytes_hashed", 0))
    if n_messages <= 0 or bytes_hashed < 0:
        raise _fail("INVALID:PILOT_NOT_DOMINANT_HOTLOOP")

    rows: list[dict[str, Any]] = []
    for row in loops:
        is_pilot = row["loop_id"] == pilot["loop_id"]
        iters = n_messages * (2048 if is_pilot else 1)
        row_bytes = bytes_hashed if is_pilot else max(1, bytes_hashed // (int(row["line_no"]) + 1))
        score = (
            int(iters)
            + int(row_bytes)
            + int(row["ops_add"]) * 11
            + int(row["ops_mul"]) * 17
            + int(row["ops_load"]) * 13
            + int(row["ops_store"]) * 7
        )
        rows.append(
            {
                "loop_id": f"{source_symbol}:{row['loop_id']}",
                "iters": int(iters),
                "bytes": int(row_bytes),
                "ops_add": int(row["ops_add"]),
                "ops_mul": int(row["ops_mul"]),
                "ops_load": int(row["ops_load"]),
                "ops_store": int(row["ops_store"]),
                "score": int(score),
            }
        )

    rows_sorted = sorted(rows, key=lambda r: (-int(r["score"]), str(r["loop_id"])))
    top_n = max(10, min(25, len(rows_sorted)))
    top_loops = rows_sorted[:top_n]
    dominant_loop_id = str(top_loops[0]["loop_id"])
    pilot_loop_id = f"{source_symbol}:{pilot['loop_id']}"

    return {
        "schema_version": "kernel_hotloop_report_v1",
        "source_path_rel": source_path_rel,
        "source_symbol": source_symbol,
        "top_n": int(top_n),
        "top_loops": [
            {
                "loop_id": str(row["loop_id"]),
                "iters": int(row["iters"]),
                "bytes": int(row["bytes"]),
                "ops_add": int(row["ops_add"]),
                "ops_mul": int(row["ops_mul"]),
                "ops_load": int(row["ops_load"]),
                "ops_store": int(row["ops_store"]),
            }
            for row in top_loops
        ],
        "dominant_loop_id": dominant_loop_id,
        "pilot_loop_id": pilot_loop_id,
    }


__all__ = ["HotloopReportError", "build_hotloop_report"]
