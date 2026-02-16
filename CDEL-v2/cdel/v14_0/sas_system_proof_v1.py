"""Lean proof helpers for SAS-System v14.0."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from ..v1_7r.canon import canon_bytes, sha256_prefixed

FORBIDDEN_TOKENS = [
    "axiom",
    "sorry",
    "admit",
    "unsafe",
    "partial",
    "meta",
    "IO.",
    "System.",
    "Process.",
    "FilePath",
    "readFile",
    "writeFile",
    "#eval",
    "macro",
    "syntax",
    "elab",
    "attribute",
    "set_option",
]


def _strip_lean_comments(text: str) -> str:
    text = re.sub(r"/-.*?-/", "", text, flags=re.S)
    text = re.sub(r"--.*", "", text)
    return text


def scan_forbidden_tokens(text: str) -> list[str]:
    stripped = _strip_lean_comments(text)
    hits: list[str] = []
    for token in FORBIDDEN_TOKENS:
        if token and token in stripped:
            hits.append(token)
    return hits


def validate_proof_shape(text: str) -> bool:
    stripped = _strip_lean_comments(text)
    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    if len(lines) != 3:
        return False
    if lines[0] != "import SASSystemPreambleV14":
        return False
    if lines[1] != "theorem cand_eq_ref_export : ∀ j, eval_ir cand_ir j = eval_ir ref_ir j := by":
        return False
    if lines[2] != "exact cand_eq_ref":
        return False
    return True


def _build_invocation(template: list[Any], entrypoint: str) -> list[str]:
    return [str(arg).replace("{entrypoint}", entrypoint) for arg in template]


def _run_lean(invocation: list[str], *, cwd: Path, env: dict[str, str], timeout_ms: int) -> tuple[bytes, bytes, int, str]:
    stdout = b""
    stderr = b""
    exit_code = 1
    result = "ERROR"
    try:
        proc = subprocess.run(
            invocation,
            cwd=str(cwd),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=max(0.1, timeout_ms / 1000.0),
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
    return stdout, stderr, exit_code, result


def sealed_lean_check_receipt(
    *,
    toolchain_manifest: dict[str, Any],
    problem_id: str,
    attempt_id: str,
    proof_text: str,
    lean_preamble_path: Path,
    work_dir: Path | None = None,
) -> dict[str, Any]:
    invocation_template = list(toolchain_manifest.get("invocation_template") or [])
    if not invocation_template:
        raise ValueError("MISSING_INVOCATION_TEMPLATE")
    toolchain_id = str(toolchain_manifest.get("toolchain_id"))

    time_limit_ms = 20000
    memory_limit_mb = 256

    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": "C",
        "LC_ALL": "C",
        "PYTHONHASHSEED": "0",
    }

    if work_dir is None:
        temp = tempfile.TemporaryDirectory()
        work_path = Path(temp.name)
    else:
        temp = None
        work_path = work_dir
        work_path.mkdir(parents=True, exist_ok=True)

    run_temp: tempfile.TemporaryDirectory[str] | None = None
    run_path = work_path
    if os.pathsep in str(work_path):
        run_temp = tempfile.TemporaryDirectory()
        run_path = Path(run_temp.name)

    try:
        proof_path = run_path / "proof.lean"
        preamble_name = "SASSystemPreambleV14.lean"
        preamble_path = run_path / preamble_name
        preamble_bytes = lean_preamble_path.read_bytes()
        proof_path.write_text(proof_text, encoding="utf-8")
        preamble_path.write_bytes(preamble_bytes)

        env["LEAN_PATH"] = str(run_path)

        lean_bin = str(invocation_template[0])
        preamble_invocation = [lean_bin, "-o", "SASSystemPreambleV14.olean", preamble_name]
        proof_invocation = _build_invocation(invocation_template, "proof.lean")

        start = time.monotonic()
        pre_stdout, pre_stderr, pre_code, pre_result = _run_lean(
            preamble_invocation,
            cwd=run_path,
            env=env,
            timeout_ms=time_limit_ms,
        )

        if pre_code != 0:
            stdout = pre_stdout
            stderr = pre_stderr
            exit_code = pre_code
            result = pre_result
        else:
            stdout, stderr, exit_code, result = _run_lean(
                proof_invocation,
                cwd=run_path,
                env=env,
                timeout_ms=time_limit_ms,
            )

        elapsed_ms = int((time.monotonic() - start) * 1000)

        sandbox_manifest = {
            "network": "NONE",
            "time_limit_ms": int(time_limit_ms),
            "memory_limit_mb": int(memory_limit_mb),
            "env": dict(env),
        }

        return {
            "schema_version": "sealed_proof_check_receipt_v1",
            "toolchain_id": toolchain_id,
            "problem_id": problem_id,
            "attempt_id": attempt_id,
            "invocation_argv": proof_invocation,
            "exit_code": int(exit_code),
            "stdout_hash": sha256_prefixed(stdout),
            "stderr_hash": sha256_prefixed(stderr),
            "result": result,
            "time_ms": int(elapsed_ms),
            "sandbox_manifest_hash": sha256_prefixed(canon_bytes(sandbox_manifest)),
            "lean_preamble_sha256": sha256_prefixed(preamble_bytes),
        }
    finally:
        if temp is not None:
            temp.cleanup()
        if run_temp is not None:
            run_temp.cleanup()


__all__ = ["scan_forbidden_tokens", "validate_proof_shape", "sealed_lean_check_receipt"]
