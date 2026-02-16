#!/usr/bin/env python3
"""Gate suite changes by baseline quality metrics."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


DEFAULT_ALLOWED_DELTA = 0.2
DEFAULT_MAX_TIMEOUT_FRAC = 0.1
DEFAULT_MAX_SECURITY_FRAC = 0.1


def _git_show(commit: str, path: str) -> str | None:
    try:
        return subprocess.check_output(["git", "show", f"{commit}:{path}"], text=True).strip()
    except subprocess.CalledProcessError:
        return None


def _load_pointer(content: str) -> dict:
    data = json.loads(content)
    if not isinstance(data, dict):
        raise ValueError("pointer must be object")
    return data


def _parse_suite_hash(pointer: dict) -> str:
    suite_hash = pointer.get("suite_hash")
    if not isinstance(suite_hash, str) or not suite_hash:
        raise ValueError("suite_hash missing")
    return suite_hash


def _load_suite_rows(text: str) -> list[dict]:
    rows: list[dict] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        data = json.loads(line)
        if not isinstance(data, dict):
            raise ValueError(f"suite row {idx} must be object")
        rows.append(data)
    return rows


def _baseline_episode_passes(spec: dict) -> bool:
    tests = spec.get("tests")
    if not isinstance(tests, list) or not tests:
        return False
    for case in tests:
        if not isinstance(case, dict):
            return False
        expected = case.get("expected")
        if expected is True:
            return False
        if expected is False:
            continue
        if isinstance(expected, int):
            if expected != 0:
                return False
        else:
            return False
    return True


def _baseline_success_rate(rows: list[dict]) -> float:
    if not rows:
        return 0.0
    successes = sum(1 for spec in rows if _baseline_episode_passes(spec))
    return successes / len(rows)


def _tag_fraction(rows: list[dict], tag: str) -> float:
    if not rows:
        return 0.0
    count = 0
    for spec in rows:
        tags = spec.get("tags")
        if isinstance(tags, list) and tag in tags:
            count += 1
    return count / len(rows)


def gate_quality(
    *,
    base_rows: list[dict],
    head_rows: list[dict],
    allowed_delta: float,
    min_size_delta: int,
    max_timeout_frac: float,
    max_security_frac: float,
) -> dict:
    base_len = len(base_rows)
    head_len = len(head_rows)
    if head_len < base_len + min_size_delta:
        raise ValueError("suite size regression")

    base_rate = _baseline_success_rate(base_rows)
    head_rate = _baseline_success_rate(head_rows)
    delta = head_rate - base_rate
    if abs(delta) > allowed_delta:
        raise ValueError("baseline pass rate drift beyond threshold")

    timeout_frac = _tag_fraction(head_rows, "timeout")
    security_frac = _tag_fraction(head_rows, "security")
    if timeout_frac > max_timeout_frac:
        raise ValueError("timeout tag fraction exceeds cap")
    if security_frac > max_security_frac:
        raise ValueError("security tag fraction exceeds cap")

    return {
        "base_rate": base_rate,
        "head_rate": head_rate,
        "delta": delta,
        "base_episodes": base_len,
        "head_episodes": head_len,
        "timeout_frac": timeout_frac,
        "security_frac": security_frac,
    }


def check_suite_quality_gate(
    *,
    repo_root: Path,
    base_sha: str,
    head_sha: str,
    pointer_path: Path,
    allowed_delta: float,
    min_size_delta: int,
    max_timeout_frac: float,
    max_security_frac: float,
) -> dict:
    base_pointer_text = _git_show(base_sha, str(pointer_path))
    head_pointer_text = _git_show(head_sha, str(pointer_path))
    if not base_pointer_text or not head_pointer_text:
        raise ValueError("missing pointer content for suite gate")

    base_hash = _parse_suite_hash(_load_pointer(base_pointer_text))
    head_hash = _parse_suite_hash(_load_pointer(head_pointer_text))

    base_suite_text = _git_show(base_sha, f"sealed_suites/{base_hash}.jsonl")
    head_suite_text = _git_show(head_sha, f"sealed_suites/{head_hash}.jsonl")
    if base_suite_text is None or head_suite_text is None:
        raise ValueError("suite bytes missing for gate evaluation")

    base_rows = _load_suite_rows(base_suite_text)
    head_rows = _load_suite_rows(head_suite_text)

    result = gate_quality(
        base_rows=base_rows,
        head_rows=head_rows,
        allowed_delta=allowed_delta,
        min_size_delta=min_size_delta,
        max_timeout_frac=max_timeout_frac,
        max_security_frac=max_security_frac,
    )
    result.update({"base_suite_hash": base_hash, "head_suite_hash": head_hash})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Suite quality gate for pyut dev suites.")
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--pointer-path", default="suites/pyut_dev_current.json")
    parser.add_argument("--allowed-delta", type=float, default=DEFAULT_ALLOWED_DELTA)
    parser.add_argument("--min-size-delta", type=int, default=0)
    parser.add_argument("--max-timeout-frac", type=float, default=DEFAULT_MAX_TIMEOUT_FRAC)
    parser.add_argument("--max-security-frac", type=float, default=DEFAULT_MAX_SECURITY_FRAC)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    try:
        result = check_suite_quality_gate(
            repo_root=repo_root,
            base_sha=args.base_sha,
            head_sha=args.head_sha,
            pointer_path=Path(args.pointer_path),
            allowed_delta=args.allowed_delta,
            min_size_delta=args.min_size_delta,
            max_timeout_frac=args.max_timeout_frac,
            max_security_frac=args.max_security_frac,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=os.sys.stderr)
        return 1

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
