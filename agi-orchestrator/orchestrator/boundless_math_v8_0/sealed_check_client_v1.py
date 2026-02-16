"""Sealed proof check client (v8.0)."""

from __future__ import annotations

import hashlib
import subprocess
import time
from typing import Callable
from pathlib import Path
from typing import Any, Tuple

from cdel.v1_7r.canon import canon_bytes, write_canon_json
from cdel.v8_0.sealed_proofcheck import compute_sealed_receipt_hash


class SealedCheckError(RuntimeError):
    pass


def _sha256_prefixed(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _limits_preexec(time_limit_ms: int, memory_limit_mb: int) -> Callable[[], None]:
    def _apply() -> None:
        try:
            import resource  # macOS/UNIX only

            cpu_seconds = max(1, int((time_limit_ms + 999) / 1000))
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
            mem_bytes = int(memory_limit_mb) * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
        except Exception:
            return

    return _apply


def _write_log(logs_dir: Path, *, suffix: str, data: bytes) -> str:
    logs_dir.mkdir(parents=True, exist_ok=True)
    digest = _sha256_prefixed(data)
    name = f"sha256_{digest.split(':',1)[1]}.{suffix}.log"
    path = logs_dir / name
    path.write_bytes(data)
    return digest


def run_sealed_check(
    *,
    sealed_dir: Path,
    logs_dir: Path,
    toolchain_manifest: dict[str, Any],
    attempt_id: str,
    problem_id: str,
    entrypoint: str,
    proof_path: Path,
    time_limit_ms: int,
    memory_limit_mb: int,
) -> Tuple[dict[str, Any], str]:
    sealed_dir.mkdir(parents=True, exist_ok=True)
    entrypoint_path = Path(entrypoint)

    invocation = list(toolchain_manifest.get("invocation_template") or [])
    invocation = [str(arg).replace("{entrypoint}", str(entrypoint_path)) for arg in invocation]

    env = {
        "PATH": "/usr/bin:/bin",
        "LANG": "C",
        "LC_ALL": "C",
        "PYTHONHASHSEED": "0",
    }

    start = time.monotonic()
    stdout = b""
    stderr = b""
    exit_code = 1
    result = "ERROR"
    try:
        proc = subprocess.run(
            invocation,
            cwd=str(entrypoint_path.parent),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=max(0.1, time_limit_ms / 1000.0),
            preexec_fn=_limits_preexec(time_limit_ms, memory_limit_mb),
            check=False,
        )
        stdout = proc.stdout or b""
        stderr = proc.stderr or b""
        exit_code = int(proc.returncode)
        result = "PASS" if exit_code == 0 else "FAIL"
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or b""
        stderr = exc.stderr or b""
        exit_code = 124
        result = "TIMEOUT"
    except OSError as exc:
        stderr = str(exc).encode("utf-8")
        exit_code = 127
        result = "ERROR"

    elapsed_ms = int((time.monotonic() - start) * 1000)
    stdout_hash = _write_log(logs_dir, suffix="stdout", data=stdout)
    stderr_hash = _write_log(logs_dir, suffix="stderr", data=stderr)

    sandbox_manifest = {
        "network": "NONE",
        "time_limit_ms": int(time_limit_ms),
        "memory_limit_mb": int(memory_limit_mb),
        "env": dict(env),
    }
    sandbox_manifest_hash = _sha256_prefixed(canon_bytes(sandbox_manifest))

    receipt = {
        "schema_version": "sealed_proof_check_receipt_v1",
        "toolchain_id": toolchain_manifest.get("toolchain_id"),
        "problem_id": problem_id,
        "attempt_id": attempt_id,
        "invocation_argv": invocation,
        "exit_code": exit_code,
        "stdout_hash": stdout_hash,
        "stderr_hash": stderr_hash,
        "result": result,
        "time_ms": elapsed_ms,
        "sandbox_manifest_hash": sandbox_manifest_hash,
    }

    receipt_hash = compute_sealed_receipt_hash(receipt)
    path = sealed_dir / f"sha256_{receipt_hash.split(':',1)[1]}.sealed_proof_check_receipt_v1.json"
    write_canon_json(path, receipt)
    return receipt, receipt_hash


__all__ = ["run_sealed_check", "SealedCheckError"]
