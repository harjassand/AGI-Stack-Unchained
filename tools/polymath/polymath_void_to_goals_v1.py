#!/usr/bin/env python3
"""Deterministic scheduler: polymath void rows to boundless goal injections."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


_DEFAULT_VOID_REPORT = "polymath/registry/polymath_void_report_v1.jsonl"
_DEFAULT_ROUTER_PATH = "polymath/registry/void_topic_router_v1.json"
_GOAL_ID_PATTERN = re.compile(r"^goal_auto_00_void_(math|science)_([a-z0-9_]+)_([0-9]+)$")
_ROUTE_TO_CAPABILITY = {
    "MATH": "RSI_BOUNDLESS_MATH_V8",
    "SCIENCE": "RSI_BOUNDLESS_SCIENCE_V9",
}


def _normalize_topic_id(raw: str) -> str:
    out: list[str] = []
    prev_sep = False
    for ch in str(raw).strip().lower():
        if ch.isalnum():
            out.append(ch)
            prev_sep = False
            continue
        if not prev_sep:
            out.append("_")
            prev_sep = True
    slug = "".join(out).strip("_")
    return slug or "topic_unknown"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _load_goal_queue(path: Path) -> dict[str, Any]:
    if path.exists() and path.is_file():
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        payload = {"schema_version": "omega_goal_queue_v1", "goals": []}
    if not isinstance(payload, dict):
        payload = {"schema_version": "omega_goal_queue_v1", "goals": []}
    if str(payload.get("schema_version", "")).strip() != "omega_goal_queue_v1":
        payload["schema_version"] = "omega_goal_queue_v1"
    goals = payload.get("goals")
    if not isinstance(goals, list):
        payload["goals"] = []
    return payload


def _load_router(router_path: Path) -> dict[str, Any]:
    if not router_path.exists() or not router_path.is_file():
        return {
            "schema_version": "void_topic_router_v1",
            "default_route": "SCIENCE",
            "topic_overrides": {},
            "keyword_rules": [],
        }
    payload = json.loads(router_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("SCHEMA_FAIL")
    return payload


def _route_topic(*, topic_id: str, topic_name: str, router: dict[str, Any]) -> str:
    overrides = router.get("topic_overrides")
    if isinstance(overrides, dict):
        for key in (topic_id, _normalize_topic_id(topic_id)):
            value = str(overrides.get(key, "")).strip().upper()
            if value in _ROUTE_TO_CAPABILITY:
                return value

    rules = router.get("keyword_rules")
    text_blob = f"{topic_id} {topic_name}".lower()
    if isinstance(rules, list):
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            route = str(rule.get("route", "")).strip().upper()
            if route not in _ROUTE_TO_CAPABILITY:
                continue
            keywords = rule.get("contains_any")
            if not isinstance(keywords, list):
                continue
            for keyword in keywords:
                key = str(keyword).strip().lower()
                if key and key in text_blob:
                    return route

    default_route = str(router.get("default_route", "SCIENCE")).strip().upper()
    if default_route in _ROUTE_TO_CAPABILITY:
        return default_route
    return "SCIENCE"


def _existing_pending_topic_ids(goals: list[dict[str, Any]]) -> set[str]:
    out: set[str] = set()
    for row in goals:
        if not isinstance(row, dict):
            continue
        if str(row.get("status", "PENDING")).strip() != "PENDING":
            continue
        topic_meta = str(row.get("topic_id", "")).strip()
        if topic_meta:
            out.add(_normalize_topic_id(topic_meta))
        goal_id = str(row.get("goal_id", "")).strip()
        match = _GOAL_ID_PATTERN.match(goal_id)
        if match:
            out.add(str(match.group(2)))
    return out


def _void_rows_sorted(void_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def _row_key(row: dict[str, Any]) -> tuple[int, str]:
        score_obj = row.get("void_score_q32")
        score_q = 0
        if isinstance(score_obj, dict):
            score_q = int(score_obj.get("q", 0))
        topic_id = str(row.get("topic_id", "")).strip()
        return (-score_q, topic_id)

    filtered = [row for row in void_rows if isinstance(row, dict)]
    return sorted(filtered, key=_row_key)


def inject_void_goals(
    *,
    void_report_path: Path,
    out_goal_queue_effective_path: Path,
    router_path: Path,
    max_goals: int,
    tick_u64: int,
) -> dict[str, Any]:
    rows = _void_rows_sorted(_load_jsonl(void_report_path))
    goal_queue = _load_goal_queue(out_goal_queue_effective_path)
    goals = goal_queue.get("goals")
    if not isinstance(goals, list):
        goals = []
        goal_queue["goals"] = goals
    router = _load_router(router_path)

    existing_pending_topic_ids = _existing_pending_topic_ids(goals)
    to_add: list[dict[str, str]] = []
    max_rows = max(0, int(max_goals))
    for row in rows:
        if len(to_add) >= max_rows:
            break
        topic_id_raw = str(row.get("topic_id", "")).strip()
        topic_name = str(row.get("topic_name", "")).strip()
        topic_id = _normalize_topic_id(topic_id_raw)
        if not topic_id or topic_id in existing_pending_topic_ids:
            continue
        route = _route_topic(topic_id=topic_id_raw, topic_name=topic_name, router=router)
        capability_id = _ROUTE_TO_CAPABILITY.get(route, "RSI_BOUNDLESS_SCIENCE_V9")
        label = "math" if route == "MATH" else "science"
        goal_id = f"goal_auto_00_void_{label}_{topic_id}_{int(tick_u64):04d}"
        to_add.append(
            {
                "goal_id": goal_id,
                "capability_id": capability_id,
                "status": "PENDING",
                "topic_id": topic_id_raw,
            }
        )
        existing_pending_topic_ids.add(topic_id)

    if to_add:
        goals.extend(to_add)
    out_goal_queue_effective_path.parent.mkdir(parents=True, exist_ok=True)
    out_goal_queue_effective_path.write_text(
        json.dumps(goal_queue, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    return {
        "schema_version": "omega_void_to_goals_report_v1",
        "void_report_path": void_report_path.as_posix(),
        "router_path": router_path.as_posix(),
        "out_goal_queue_effective_path": out_goal_queue_effective_path.as_posix(),
        "max_goals_u64": int(max_rows),
        "tick_u64": int(tick_u64),
        "rows_scanned_u64": int(len(rows)),
        "goals_injected_u64": int(len(to_add)),
        "injected_goals": to_add,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="polymath_void_to_goals_v1")
    parser.add_argument("--void_report_path", default=_DEFAULT_VOID_REPORT)
    parser.add_argument("--out_goal_queue_effective_path", required=True)
    parser.add_argument("--router_path", default=_DEFAULT_ROUTER_PATH)
    parser.add_argument("--max_goals", type=int, default=2)
    parser.add_argument("--tick_u64", type=int, required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = inject_void_goals(
        void_report_path=Path(args.void_report_path).expanduser().resolve(),
        out_goal_queue_effective_path=Path(args.out_goal_queue_effective_path).expanduser().resolve(),
        router_path=Path(args.router_path).expanduser().resolve(),
        max_goals=max(0, int(args.max_goals)),
        tick_u64=max(0, int(args.tick_u64)),
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
