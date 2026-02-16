"""Suite mining helpers for hard-case extraction."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from blake3 import blake3

_EDGE_INTS = {0, 1, -1}
_LARGE_INT_THRESHOLD = 10


@dataclass(frozen=True)
class MinedCase:
    payload: dict
    key: str


def mine_cases(
    *,
    run_dir: Path,
    domain: str,
    max_episodes: int = 50,
    suites_dir: Path | None = None,
) -> list[dict]:
    """Return mined suite episodes for a run directory."""
    if domain != "python-ut-v1":
        return []
    manifest = _load_manifest(run_dir)
    root_dir = Path(manifest.get("root_dir") or run_dir)
    suite_hash = manifest.get("dev_suite_hash")
    if not isinstance(suite_hash, str) or not suite_hash:
        raise ValueError("dev_suite_hash missing from manifest")
    suite_path = _suite_path(root_dir, suite_hash, suites_dir)
    suite_rows = _parse_pyut_suite(suite_path)

    mined: list[MinedCase] = []
    seen: set[str] = set()
    for row in _iter_artifact_rows(run_dir):
        payload = _pyut_case_from_row(row, suite_rows)
        if payload is None:
            continue
        key = _dedup_key(payload)
        if key in seen:
            continue
        seen.add(key)
        mined.append(MinedCase(payload=payload, key=key))
        if len(mined) >= max_episodes:
            break
    return _assign_episode_indices([item.payload for item in mined])


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def _load_manifest(run_dir: Path) -> dict:
    path = run_dir / "manifest.json"
    if not path.exists():
        raise ValueError(f"manifest missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("manifest must be object")
    return payload


def _suite_path(root_dir: Path, suite_hash: str, suites_dir: Path | None) -> Path:
    if suites_dir is not None:
        return suites_dir / f"{suite_hash}.jsonl"
    return root_dir / "sealed_suites" / f"{suite_hash}.jsonl"


def _parse_pyut_suite(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _iter_artifact_rows(run_dir: Path) -> Iterable[dict]:
    candidates_dir = run_dir / "candidates"
    if not candidates_dir.exists():
        return []
    rows: list[dict] = []
    for candidate_dir in sorted(p for p in candidates_dir.iterdir() if p.is_dir()):
        artifact_dir = candidate_dir / "dev_artifacts"
        if not artifact_dir.exists():
            continue
        for path in sorted(artifact_dir.glob("*.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line:
                    continue
                payload = json.loads(line)
                if isinstance(payload, dict):
                    rows.append(payload)
    return rows


def _pyut_case_from_row(row: dict, suite_rows: list[dict]) -> dict | None:
    if row.get("baseline_success") is not True:
        return None
    if row.get("candidate_success") is not False:
        return None
    episode = row.get("episode")
    if not isinstance(episode, int) or episode < 0 or episode >= len(suite_rows):
        return None
    failed_idx = row.get("candidate_failed_test")
    if not isinstance(failed_idx, int):
        return None
    suite = suite_rows[episode]
    tests = suite.get("tests")
    if not isinstance(tests, list) or failed_idx < 0 or failed_idx >= len(tests):
        return None
    test = tests[failed_idx]
    args = test.get("args")
    expected = test.get("expected")
    if not isinstance(args, list):
        return None
    task_id = suite.get("task_id")
    fn_name = suite.get("fn_name")
    signature = suite.get("signature")
    if not isinstance(task_id, str) or not isinstance(fn_name, str) or not isinstance(signature, str):
        return None

    tags: list[str] = []
    if row.get("candidate_timeout") is True or row.get("candidate_error") == "timeout":
        tags.append("timeout")
    if row.get("candidate_error") == "security_violation":
        tags.append("security_violation")
    if row.get("candidate_error_detail") in {"ImportBlocked", "SecurityViolation"}:
        tags.append("security_violation")

    ints = list(_iter_ints([args, expected]))
    if any(value in _EDGE_INTS for value in ints):
        tags.append("edge_value")
    if any(abs(value) >= _LARGE_INT_THRESHOLD for value in ints):
        tags.append("large_int")

    payload = {
        "episode": 0,
        "task_id": task_id,
        "fn_name": fn_name,
        "signature": signature,
        "tests": [{"args": args, "expected": expected}],
    }
    if tags:
        payload["tags"] = sorted(set(tags))
    return payload


def _assign_episode_indices(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for idx, row in enumerate(rows):
        payload = dict(row)
        payload["episode"] = idx
        out.append(payload)
    return out


def _dedup_key(payload: dict) -> str:
    data = {
        "task_id": payload.get("task_id"),
        "fn_name": payload.get("fn_name"),
        "args": _first_test(payload).get("args"),
        "expected": _first_test(payload).get("expected"),
    }
    raw = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return blake3(raw).hexdigest()


def _first_test(payload: dict) -> dict:
    tests = payload.get("tests")
    if isinstance(tests, list) and tests:
        first = tests[0]
        if isinstance(first, dict):
            return first
    return {}


def _iter_ints(value: object) -> Iterable[int]:
    if isinstance(value, bool):
        return []
    if isinstance(value, int):
        return [value]
    if isinstance(value, list):
        items: list[int] = []
        for item in value:
            items.extend(_iter_ints(item))
        return items
    if isinstance(value, dict):
        items = []
        for item in value.values():
            items.extend(_iter_ints(item))
        return items
    return []
