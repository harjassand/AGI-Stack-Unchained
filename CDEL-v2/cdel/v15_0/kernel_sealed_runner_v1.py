"""Sealed execution helpers for kernel and worker commands."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .kernel_pinning_v1 import load_toolchain_manifest, run_pinned


class KernelSealedRunnerError(RuntimeError):
    pass


def _fail(reason: str) -> None:
    raise KernelSealedRunnerError(reason)


def run_worker(
    *,
    manifest_path: Path,
    argv_tail: list[str] | None = None,
    stdin_json: str | None = None,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    manifest = load_toolchain_manifest(manifest_path)
    invocation = list(manifest["invocation_template"])
    if argv_tail:
        invocation.extend(argv_tail)

    if env is None:
        env = {}

    result = run_pinned(invocation, expected_hash=manifest["checker_executable_hash"])
    if stdin_json is not None:
        # `run_pinned` currently does not pass stdin; enforce deterministic no-stdin policy
        # until a stdin-enabled path is required.
        if stdin_json != "":
            _fail("INVALID:SEALED_STDIN_UNSUPPORTED")
    if cwd is not None and not cwd.exists():
        _fail("INVALID:SEALED_CWD")
    return result


def run_kernel_binary(
    *,
    kernel_exe_abs: Path,
    kernel_exe_hash: str,
    run_spec_path: Path,
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    if not kernel_exe_abs.is_absolute():
        _fail("INVALID:KERNEL_PINNING")
    argv = [str(kernel_exe_abs), "run", "--run_spec", str(run_spec_path)]
    result = run_pinned(argv, expected_hash=kernel_exe_hash)
    if result.returncode not in {0, 10, 20, 30}:
        _fail(f"INVALID:KERNEL_EXIT_CODE:{result.returncode}")
    return result


def sealed_receipt_from_run(
    *,
    argv: list[str],
    returncode: int,
    stdout: str,
    stderr: str,
) -> dict[str, Any]:
    return {
        "schema_version": "kernel_sealed_run_receipt_v1",
        "argv": argv,
        "returncode": int(returncode),
        "stdout": stdout,
        "stderr": stderr,
    }


__all__ = [
    "KernelSealedRunnerError",
    "run_worker",
    "run_kernel_binary",
    "sealed_receipt_from_run",
]
