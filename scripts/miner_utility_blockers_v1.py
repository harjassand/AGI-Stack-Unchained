#!/usr/bin/env python3
"""Summarize utility blockers for counted heavy attempts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


_HEAVY_DECLARED_CLASSES = {"FRONTIER_HEAVY", "CANARY_HEAVY"}


def _load_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            out.append(payload)
    return out


def _is_sha256(value: Any) -> bool:
    text = str(value).strip()
    return text.startswith("sha256:") and len(text) == 71


def _norm_text(value: Any, default: str = "UNKNOWN") -> str:
    text = str(value).strip()
    return text if text else default


def _norm_reason(value: Any) -> str:
    return _norm_text(value, default="UNKNOWN").upper()


def _is_counted_heavy_attempt(row: dict[str, Any]) -> bool:
    declared_class = _norm_reason(row.get("declared_class"))
    if declared_class not in _HEAVY_DECLARED_CLASSES:
        return False
    return bool(row.get("frontier_attempt_counted_b", False))


def _utility_receipt_path(row: dict[str, Any]) -> Path | None:
    state_dir = Path(str(row.get("state_dir", "")).strip())
    if not state_dir.exists() or not state_dir.is_dir():
        return None
    proof_hash = str(row.get("utility_proof_hash", "")).strip()
    if _is_sha256(proof_hash):
        digest = proof_hash.split(":", 1)[1]
        rows = sorted(
            state_dir.glob(f"dispatch/*/promotion/sha256_{digest}.utility_proof_receipt_v1.json"),
            key=lambda p: p.as_posix(),
        )
        if rows:
            return rows[-1]
    rows = sorted(
        state_dir.glob("dispatch/*/promotion/sha256_*.utility_proof_receipt_v1.json"),
        key=lambda p: p.as_posix(),
    )
    if rows:
        return rows[-1]
    plain_rows = sorted(
        state_dir.glob("dispatch/*/promotion/utility_proof_receipt_v1.json"),
        key=lambda p: p.as_posix(),
    )
    if plain_rows:
        return plain_rows[-1]
    return None


def _load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or (not path.exists()) or (not path.is_file()):
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def main() -> None:
    ap = argparse.ArgumentParser(prog="miner_utility_blockers_v1")
    ap.add_argument("--run_root", required=True, help="Run root containing index/long_run_tick_index_v1.jsonl")
    ap.add_argument("--last_n", type=int, default=200)
    ap.add_argument("--top_k", type=int, default=5)
    args = ap.parse_args()

    index_path = Path(args.run_root) / "index" / "long_run_tick_index_v1.jsonl"
    rows = _load_rows(index_path)
    last_n = max(1, int(args.last_n))
    top_k = max(1, int(args.top_k))
    scope = rows[-last_n:]
    attempts = [row for row in scope if _is_counted_heavy_attempt(row)]

    hist: dict[tuple[str, str], int] = {}
    attempt_records: list[dict[str, Any]] = []
    for row in attempts:
        receipt_path = _utility_receipt_path(row)
        utility_receipt = _load_json(receipt_path)
        utility_metrics = dict((utility_receipt or {}).get("utility_metrics") or {})
        utility_thresholds = dict((utility_receipt or {}).get("utility_thresholds") or {})
        capability_id = _norm_text(
            row.get("selected_capability_id")
            or (utility_receipt or {}).get("capability_id"),
            default="UNKNOWN_CAPABILITY",
        )
        utility_reason = _norm_reason(
            row.get("utility_proof_reason_code")
            or (utility_receipt or {}).get("reason_code")
            or row.get("promotion_reason_code"),
        )
        hard_task_baseline_init_b = bool(
            utility_metrics.get("hard_task_baseline_init_b", row.get("hard_task_baseline_init_b", False))
        )
        hard_task_delta_q32 = int(
            utility_metrics.get("hard_task_delta_q32", row.get("hard_task_delta_q32", 0))
        )
        predicted_hard_task_delta_q32_raw = utility_metrics.get("predicted_hard_task_delta_q32")
        predicted_hard_task_delta_q32 = (
            int(predicted_hard_task_delta_q32_raw)
            if predicted_hard_task_delta_q32_raw is not None
            else None
        )
        key = (utility_reason, capability_id)
        hist[key] = int(hist.get(key, 0) + 1)
        attempt_records.append(
            {
                "tick_u64": int(row.get("tick_u64", 0)),
                "state_dir": str(row.get("state_dir", "")),
                "capability_id": capability_id,
                "utility_proof_reason_code": utility_reason,
                "hard_task_baseline_init_b": bool(hard_task_baseline_init_b),
                "hard_task_delta_q32": int(hard_task_delta_q32),
                "predicted_hard_task_delta_q32": predicted_hard_task_delta_q32,
                "thresholds_v1": utility_thresholds if isinstance(utility_thresholds, dict) else {},
                "utility_receipt_path": str(receipt_path) if receipt_path is not None else None,
            }
        )

    hist_items = sorted(hist.items(), key=lambda kv: (-int(kv[1]), kv[0][0], kv[0][1]))
    top_examples: list[dict[str, Any]] = []
    for (reason_code, capability_id), count in hist_items[:top_k]:
        matching = [
            row
            for row in attempt_records
            if row["utility_proof_reason_code"] == reason_code and row["capability_id"] == capability_id
        ]
        matching.sort(key=lambda row: int(row.get("tick_u64", 0)), reverse=True)
        top_examples.append(
            {
                "reason_code": reason_code,
                "capability_id": capability_id,
                "count_u64": int(count),
                "examples_v1": matching[:top_k],
            }
        )

    payload = {
        "rows_scanned_u64": int(len(scope)),
        "counted_heavy_attempts_u64": int(len(attempts)),
        "histogram_by_reason_capability": [
            {
                "reason_code": key[0],
                "capability_id": key[1],
                "count_u64": int(count),
            }
            for key, count in hist_items
        ],
        "top_examples_v1": top_examples,
    }
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
