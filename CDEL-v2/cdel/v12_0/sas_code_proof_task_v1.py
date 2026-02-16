"""Proof task helpers for SAS-CODE (v12.0)."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from ..v1_7r.canon import canon_bytes, sha256_prefixed

FORBIDDEN_TOKENS = [
    "sorry",
    "admit",
    "axiom",
    "unsafe",
    "IO.",
    "System.",
    "Process.",
    "FilePath",
    "readFile",
    "writeFile",
    "#eval",
    "#check",
    "set_option",
    "macro",
    "syntax",
    "elab",
    "attribute",
    "def Perm",
    "def Sorted",
    "def SortSpec",
    "def Multiset",
    "def Bag",
    "def SASCodeSorted",
    "theorem sorted_perm_unique",
]

SEMANTICS_TAMPER_TOKENS = [
    "def Perm",
    "def Sorted",
    "def SortSpec",
    "def Multiset",
    "def Bag",
    "def SASCodeSorted",
    "axiom",
    "def bubbleSort",
    "def mergeSort",
    "def sort_ref",
    "def sort_cand",
]

PREAMBLE_TAMPER_TOKENS = [
    "namespace List",
    "def Sorted",
    "def Perm",
    "def SortSpec",
    "def Multiset",
    "def Bag",
    "axiom",
]


def proof_text() -> str:
    return (
        "import SASCodePreambleV12\n\n"
        "namespace SASCodeAttempt\n\n"
        "theorem cand_eq_ref : ∀ xs : List Nat, sort_cand xs = sort_ref xs := by\n"
        "  intro xs\n"
        "  induction xs with\n"
        "  | nil =>\n"
        "      simp [sort_ref, sort_cand, bubbleSort, bubbleIter, mergeSort]\n"
        "  | cons x xs ih =>\n"
        "      have h1 : SASCodeSorted (sort_cand (x :: xs)) := by\n"
        "        simpa [sort_cand] using merge_sorted (x :: xs)\n"
        "      have h2 : SASCodeSorted (sort_ref (x :: xs)) := by\n"
        "        simpa [sort_ref] using bubble_sorted (x :: xs)\n"
        "      have hp : List.Perm (sort_cand (x :: xs)) (sort_ref (x :: xs)) := by\n"
        "        have pc : List.Perm (sort_cand (x :: xs)) (x :: xs) := by\n"
        "          simpa [sort_cand] using merge_perm (x :: xs)\n"
        "        have pr : List.Perm (sort_ref (x :: xs)) (x :: xs) := by\n"
        "          simpa [sort_ref] using bubble_perm (x :: xs)\n"
        "        exact pc.trans pr.symm\n"
        "      exact sorted_perm_unique h1 h2 hp\n\n"
        "end SASCodeAttempt\n"
    )


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


def scan_semantic_tamper(text: str) -> list[str]:
    stripped = _strip_lean_comments(text)
    hits: list[str] = []
    for token in SEMANTICS_TAMPER_TOKENS:
        if token and token in stripped:
            hits.append(token)
    return hits


def scan_preamble_tamper(text: str) -> list[str]:
    stripped = _strip_lean_comments(text)
    hits: list[str] = []
    for token in PREAMBLE_TAMPER_TOKENS:
        if token and token in stripped:
            hits.append(token)
    return hits


def check_required_symbols(text: str) -> list[str]:
    stripped = _strip_lean_comments(text)
    missing: list[str] = []
    if "import SASCodePreambleV12" not in stripped:
        missing.append("import SASCodePreambleV12")
    if "List.Perm" not in stripped:
        missing.append("List.Perm")
    if "SASCodeSorted" not in stripped:
        missing.append("SASCodeSorted")
    for symbol in ["sorted_perm_unique", "cand_eq_ref", "sort_ref", "sort_cand", "bubbleSort", "mergeSort"]:
        if symbol not in stripped:
            missing.append(symbol)
    return missing


def nontriviality_issues(text: str) -> list[str]:
    stripped = _strip_lean_comments(text)
    issues: list[str] = []
    if "induction xs" not in stripped:
        issues.append("MISSING_INDUCTION")
    if "sorted_perm_unique" not in stripped:
        issues.append("MISSING_UNIQUENESS")
    return issues


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


def sealed_proof_check_receipt(
    *,
    toolchain_manifest: dict[str, Any],
    problem_id: str,
    attempt_id: str,
    proof_text: str,
    lean_preamble_path: Path,
    lean_preamble_sha256: str | None = None,
    work_dir: Path | None = None,
) -> dict[str, Any]:
    invocation_template = list(toolchain_manifest.get("invocation_template") or [])
    if not invocation_template:
        raise ValueError("MISSING_INVOCATION_TEMPLATE")
    toolchain_id = str(toolchain_manifest.get("toolchain_id"))

    time_limit_ms = 20000
    memory_limit_mb = 256

    env = {
        "PATH": "/usr/bin:/bin",
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

    # Lean splits LEAN_PATH on os.pathsep (":" on macOS/Linux). Our work
    # directories include "sha256:<id>", which would be split and break imports.
    # Use a separate colon-free run directory when needed.
    run_temp: tempfile.TemporaryDirectory[str] | None = None
    run_path = work_path
    if os.pathsep in str(work_path):
        run_temp = tempfile.TemporaryDirectory()
        run_path = Path(run_temp.name)
    run_path.mkdir(parents=True, exist_ok=True)

    try:
        proof_path = run_path / "proof.lean"
        preamble_path = run_path / "SASCodePreambleV12.lean"
        proof_path.parent.mkdir(parents=True, exist_ok=True)
        preamble_path.parent.mkdir(parents=True, exist_ok=True)
        proof_path.write_text(proof_text, encoding="utf-8")
        preamble_path.write_bytes(lean_preamble_path.read_bytes())

        env["LEAN_PATH"] = str(run_path)

        lean_bin = str(invocation_template[0])
        preamble_invocation = [lean_bin, "-o", "SASCodePreambleV12.olean", "SASCodePreambleV12.lean"]
        proof_invocation = _build_invocation(invocation_template, "proof.lean")

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

        elapsed_ms = 1

        stdout_hash = sha256_prefixed(stdout)
        stderr_hash = sha256_prefixed(stderr)
        sandbox_manifest = {
            "network": "NONE",
            "time_limit_ms": int(time_limit_ms),
            "memory_limit_mb": int(memory_limit_mb),
            "env": dict(env),
        }
        sandbox_manifest_hash = sha256_prefixed(canon_bytes(sandbox_manifest))

        receipt = {
            "schema_version": "sealed_proof_check_receipt_v1",
            "toolchain_id": toolchain_id,
            "problem_id": problem_id,
            "attempt_id": attempt_id,
            "invocation_argv": proof_invocation,
            "exit_code": exit_code,
            "stdout_hash": stdout_hash,
            "stderr_hash": stderr_hash,
            "result": result,
            "time_ms": int(elapsed_ms),
            "sandbox_manifest_hash": sandbox_manifest_hash,
        }
        if lean_preamble_sha256 is not None:
            receipt["lean_preamble_sha256"] = lean_preamble_sha256
        # Always persist proof to the requested work_dir, even if we executed in a temp dir.
        if work_dir is not None and work_path != run_path:
            work_path.mkdir(parents=True, exist_ok=True)
            (work_path / "proof.lean").write_text(proof_text, encoding="utf-8")
        return receipt
    finally:
        if temp is not None:
            temp.cleanup()
        if run_temp is not None:
            run_temp.cleanup()


def compute_attempt_receipt_hash(receipt: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(receipt))


__all__ = [
    "FORBIDDEN_TOKENS",
    "SEMANTICS_TAMPER_TOKENS",
    "PREAMBLE_TAMPER_TOKENS",
    "proof_text",
    "scan_forbidden_tokens",
    "scan_semantic_tamper",
    "scan_preamble_tamper",
    "check_required_symbols",
    "nontriviality_issues",
    "sealed_proof_check_receipt",
    "compute_attempt_receipt_hash",
]
