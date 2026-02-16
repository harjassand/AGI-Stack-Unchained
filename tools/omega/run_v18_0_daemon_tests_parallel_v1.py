#!/usr/bin/env python3
"""Parallel pytest runner for omega daemon v18.0 tests.

This runner keeps full test semantics (no bypasses) and speeds up wall-clock
time by sharding files across worker processes when pytest-xdist is unavailable.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

_DEFAULT_PATTERN = "CDEL-v2/cdel/v18_0/tests_omega_daemon/test_*.py"
_SANITIZED_ENV_KEYS = (
    "OMEGA_META_CORE_ROOT",
    "OMEGA_META_CORE_ACTIVATION_MODE",
    "OMEGA_ALLOW_SIMULATE_ACTIVATION",
    "OMEGA_RUN_SEED_U64",
)


@dataclass(frozen=True)
class WorkerResult:
    worker_id: int
    return_code: int
    log_path: Path
    tests: tuple[str, ...]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _has_xdist() -> bool:
    return importlib.util.find_spec("xdist") is not None


def _normalize_paths(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        row = str(value).strip()
        if row:
            out.append(row)
    return out


def _discover_test_files(repo_root: Path, tests: list[str], pattern: str) -> list[Path]:
    if tests:
        seeds = [Path(row) for row in tests]
    else:
        seeds = [Path(pattern)]

    out: set[Path] = set()
    for seed in seeds:
        if seed.is_absolute():
            target = seed
        else:
            target = repo_root / seed

        if target.is_file():
            out.add(target.resolve())
            continue
        if target.is_dir():
            for row in sorted(target.rglob("test_*.py")):
                out.add(row.resolve())
            continue

        for row in sorted(repo_root.glob(str(seed))):
            if row.is_file():
                out.add(row.resolve())
            elif row.is_dir():
                for inner in sorted(row.rglob("test_*.py")):
                    out.add(inner.resolve())

    return sorted(out)


def _build_env(repo_root: Path, sanitize_env: bool) -> dict[str, str]:
    env = dict(os.environ)
    if sanitize_env:
        for key in _SANITIZED_ENV_KEYS:
            env.pop(key, None)

    pythonpath_entries: list[str] = [str(repo_root), str(repo_root / "CDEL-v2")]
    existing = str(env.get("PYTHONPATH", "")).strip()
    if existing:
        pythonpath_entries.extend([row for row in existing.split(":") if row])

    deduped: list[str] = []
    seen: set[str] = set()
    for row in pythonpath_entries:
        if row not in seen:
            deduped.append(row)
            seen.add(row)
    env["PYTHONPATH"] = ":".join(deduped)
    return env


def _shard_files(files: list[Path], workers: int) -> list[list[Path]]:
    shard_count = max(1, min(workers, len(files)))
    shards: list[list[Path]] = [[] for _ in range(shard_count)]
    totals = [0 for _ in range(shard_count)]

    weighted = sorted(
        ((path.stat().st_size, path) for path in files),
        key=lambda row: (-int(row[0]), str(row[1])),
    )
    for size, path in weighted:
        idx = min(range(shard_count), key=lambda i: (totals[i], i))
        shards[idx].append(path)
        totals[idx] += int(size)

    for shard in shards:
        shard.sort()
    return shards


def _run_xdist(
    *,
    repo_root: Path,
    tests: list[Path],
    workers: int,
    env: dict[str, str],
    pytest_args: list[str],
) -> int:
    cmd = [
        "pytest",
        "-q",
        "-n",
        str(max(1, workers)),
        "--dist",
        "loadfile",
        *pytest_args,
        *(str(path.relative_to(repo_root)) for path in tests),
    ]
    print("running with pytest-xdist:")
    print(" ", " ".join(cmd))
    return int(subprocess.run(cmd, cwd=repo_root, env=env, check=False).returncode)


def _run_manual_parallel(
    *,
    repo_root: Path,
    tests: list[Path],
    workers: int,
    env: dict[str, str],
    pytest_args: list[str],
    run_root: Path,
) -> int:
    shards = _shard_files(tests, workers)
    run_root.mkdir(parents=True, exist_ok=True)
    logs_dir = run_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    procs: list[tuple[int, subprocess.Popen[str], Path, tuple[str, ...]]] = []
    for idx, shard in enumerate(shards):
        worker_id = idx + 1
        worker_temp = run_root / f"worker_{worker_id:02d}" / "tmp"
        worker_cache = run_root / f"worker_{worker_id:02d}" / ".pytest_cache"
        worker_temp.mkdir(parents=True, exist_ok=True)
        worker_cache.mkdir(parents=True, exist_ok=True)
        log_path = logs_dir / f"worker_{worker_id:02d}.log"
        worker_tests = tuple(str(path.relative_to(repo_root)) for path in shard)
        cmd = [
            "pytest",
            "-q",
            f"--basetemp={worker_temp}",
            "-o",
            f"cache_dir={worker_cache}",
            *pytest_args,
            *worker_tests,
        ]
        print(f"worker {worker_id}: {len(worker_tests)} files")
        with log_path.open("w", encoding="utf-8") as fh:
            proc = subprocess.Popen(
                cmd,
                cwd=repo_root,
                env=env,
                stdout=fh,
                stderr=subprocess.STDOUT,
                text=True,
            )
        procs.append((worker_id, proc, log_path, worker_tests))

    results: list[WorkerResult] = []
    for worker_id, proc, log_path, worker_tests in procs:
        rc = int(proc.wait())
        results.append(
            WorkerResult(
                worker_id=worker_id,
                return_code=rc,
                log_path=log_path,
                tests=worker_tests,
            )
        )

    failed = [row for row in results if row.return_code != 0]
    for row in sorted(results, key=lambda r: r.worker_id):
        status = "PASS" if row.return_code == 0 else "FAIL"
        print(f"worker {row.worker_id:02d}: {status} ({len(row.tests)} files)")
        print(f"  log: {row.log_path}")

    if failed:
        print("")
        print("failing worker logs (tail):")
        for row in failed:
            print(f"-- worker {row.worker_id:02d} --")
            try:
                lines = row.log_path.read_text(encoding="utf-8").splitlines()
            except FileNotFoundError:
                lines = ["(missing log)"]
            tail = lines[-80:]
            for line in tail:
                print(line)

    return 1 if failed else 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="run_v18_0_daemon_tests_parallel_v1.py")
    parser.add_argument(
        "--workers",
        type=int,
        default=max(2, os.cpu_count() or 2),
        help="parallel worker count",
    )
    parser.add_argument(
        "--pattern",
        default=_DEFAULT_PATTERN,
        help="default glob pattern when no explicit tests are passed",
    )
    parser.add_argument(
        "--no-xdist",
        action="store_true",
        help="force manual sharding even if pytest-xdist is installed",
    )
    parser.add_argument(
        "--keep-run-dir",
        action="store_true",
        help="keep run logs/tmp after completion",
    )
    parser.add_argument(
        "--no-sanitize-env",
        action="store_true",
        help="do not clear OMEGA_* env vars before spawning workers",
    )
    parser.add_argument("tests", nargs="*", help="optional test files/dirs/globs")
    parser.add_argument(
        "--pytest-args",
        default="",
        help="extra pytest args as a raw string, e.g. \"--durations=25 -k goal\"",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    repo_root = _repo_root()
    tests = _discover_test_files(repo_root, _normalize_paths(args.tests), str(args.pattern))
    if not tests:
        print("no test files found")
        return 2

    workers = max(1, int(args.workers))
    env = _build_env(repo_root, sanitize_env=not bool(args.no_sanitize_env))
    pytest_args = shlex.split(str(args.pytest_args))
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    run_root = repo_root / "runs" / "_pytest_parallel" / f"v18_0_{timestamp}"

    print(f"repo_root: {repo_root}")
    print(f"tests: {len(tests)} files")
    print(f"workers: {workers}")
    print(f"run_root: {run_root}")

    if _has_xdist() and not bool(args.no_xdist):
        code = _run_xdist(
            repo_root=repo_root,
            tests=tests,
            workers=workers,
            env=env,
            pytest_args=pytest_args,
        )
    else:
        code = _run_manual_parallel(
            repo_root=repo_root,
            tests=tests,
            workers=workers,
            env=env,
            pytest_args=pytest_args,
            run_root=run_root,
        )

    if code == 0 and not bool(args.keep_run_dir) and run_root.exists():
        shutil.rmtree(run_root, ignore_errors=True)
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())
