#!/usr/bin/env python3
"""Diff two suite JSONL files with deterministic output."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from blake3 import blake3


@dataclass(frozen=True)
class SuiteDiff:
    old_count: int
    new_count: int
    added: list[str]
    removed: list[str]
    added_tags: dict[str, int]
    removed_tags: dict[str, int]
    added_tasks: dict[str, int]
    removed_tasks: dict[str, int]


def _canonical_json(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _hash_episode(obj: object) -> str:
    return blake3(_canonical_json(obj).encode("utf-8")).hexdigest()


def _collect_ints(obj: object) -> list[int]:
    values: list[int] = []
    if isinstance(obj, int):
        values.append(obj)
    elif isinstance(obj, list):
        for item in obj:
            values.extend(_collect_ints(item))
    elif isinstance(obj, dict):
        for val in obj.values():
            values.extend(_collect_ints(val))
    return values


def _collect_valuejson_ints(obj: object) -> list[int]:
    values: list[int] = []
    if isinstance(obj, dict) and obj.get("tag") == "int":
        val = obj.get("value")
        if isinstance(val, int):
            values.append(val)
    elif isinstance(obj, dict) and obj.get("tag") in {"bool", "nil"}:
        return values
    elif isinstance(obj, dict):
        for val in obj.values():
            values.extend(_collect_valuejson_ints(val))
    elif isinstance(obj, list):
        for item in obj:
            values.extend(_collect_valuejson_ints(item))
    return values


def _infer_tags(episode: dict) -> set[str]:
    tags: set[str] = set()
    raw_tags = episode.get("tags")
    if isinstance(raw_tags, list):
        for item in raw_tags:
            if isinstance(item, str) and item:
                tags.add(item)

    ints: list[int] = []
    if "tests" in episode:
        for test in episode.get("tests", []):
            if isinstance(test, dict):
                ints.extend(_collect_ints(test.get("args", [])))
                ints.extend(_collect_ints(test.get("expected")))
    elif "args" in episode and "target" in episode:
        ints.extend(_collect_valuejson_ints(episode.get("args")))
        ints.extend(_collect_valuejson_ints(episode.get("target")))
    elif "start" in episode and "goal" in episode:
        ints.extend(_collect_ints(episode.get("start")))
        ints.extend(_collect_ints(episode.get("goal")))
        ints.extend(_collect_ints(episode.get("walls")))

    if any(val in (-1, 0, 1) for val in ints):
        tags.add("edge")
    if any(abs(val) >= 100 for val in ints):
        tags.add("large-int")

    if episode.get("timeout") is True:
        tags.add("timeout")
    if "security" in json.dumps(episode, sort_keys=True):
        tags.add("security")

    if not tags:
        tags.add("uncategorized")
    return tags


def _task_key(episode: dict) -> str | None:
    task_id = episode.get("task_id")
    fn_name = episode.get("fn_name")
    if isinstance(task_id, str) and isinstance(fn_name, str):
        return f"{task_id}:{fn_name}"
    return None


def _load_suite(path: Path) -> list[dict]:
    episodes: list[dict] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path} line {line_no} invalid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"{path} line {line_no} must be an object")
        episodes.append(data)
    return episodes


def _resolve_suite_arg(arg: str, *, repo_root: Path) -> Path:
    path = Path(arg)
    if path.exists():
        return path
    candidate = repo_root / "sealed_suites" / f"{arg}.jsonl"
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"suite not found: {arg}")


def compute_suite_diff(old_path: Path, new_path: Path) -> SuiteDiff:
    old_episodes = _load_suite(old_path)
    new_episodes = _load_suite(new_path)

    old_map = { _hash_episode(ep): ep for ep in old_episodes }
    new_map = { _hash_episode(ep): ep for ep in new_episodes }

    added_hashes = sorted(set(new_map) - set(old_map))
    removed_hashes = sorted(set(old_map) - set(new_map))

    def count_tags(hashes: list[str], episodes: dict[str, dict]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for key in hashes:
            for tag in _infer_tags(episodes[key]):
                counts[tag] = counts.get(tag, 0) + 1
        return dict(sorted(counts.items()))

    def count_tasks(hashes: list[str], episodes: dict[str, dict]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for key in hashes:
            task = _task_key(episodes[key])
            if task:
                counts[task] = counts.get(task, 0) + 1
        return dict(sorted(counts.items()))

    return SuiteDiff(
        old_count=len(old_episodes),
        new_count=len(new_episodes),
        added=added_hashes,
        removed=removed_hashes,
        added_tags=count_tags(added_hashes, new_map),
        removed_tags=count_tags(removed_hashes, old_map),
        added_tasks=count_tasks(added_hashes, new_map),
        removed_tasks=count_tasks(removed_hashes, old_map),
    )


def render_report(diff: SuiteDiff) -> str:
    lines = [
        f"old_episodes: {diff.old_count}",
        f"new_episodes: {diff.new_count}",
        f"added: {len(diff.added)}",
        f"removed: {len(diff.removed)}",
    ]

    if diff.added:
        lines.append("added_hashes:")
        lines.extend(f"  {item}" for item in diff.added)
    if diff.removed:
        lines.append("removed_hashes:")
        lines.extend(f"  {item}" for item in diff.removed)

    if diff.added_tags:
        lines.append("added_tags:")
        lines.extend(f"  {key}: {value}" for key, value in diff.added_tags.items())
    if diff.removed_tags:
        lines.append("removed_tags:")
        lines.extend(f"  {key}: {value}" for key, value in diff.removed_tags.items())

    if diff.added_tasks:
        lines.append("added_tasks:")
        lines.extend(f"  {key}: {value}" for key, value in diff.added_tasks.items())
    if diff.removed_tasks:
        lines.append("removed_tasks:")
        lines.extend(f"  {key}: {value}" for key, value in diff.removed_tasks.items())

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Diff two suite JSONL files.")
    parser.add_argument("--old", required=True, help="Suite hash or path for old suite.")
    parser.add_argument("--new", required=True, help="Suite hash or path for new suite.")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    old_path = _resolve_suite_arg(args.old, repo_root=repo_root)
    new_path = _resolve_suite_arg(args.new, repo_root=repo_root)

    diff = compute_suite_diff(old_path, new_path)
    print(render_report(diff), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
