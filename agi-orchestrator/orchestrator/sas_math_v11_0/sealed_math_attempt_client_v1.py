"""Client to run sealed SAS-MATH attempt worker (v11.0)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Tuple

from cdel.v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed
from cdel.v8_0.math_attempts import compute_attempt_id


class SealedAttemptError(RuntimeError):
    pass


def _fail(reason: str) -> None:
    raise SealedAttemptError(reason)


def _build_attempt_id(
    *,
    problem_id: str,
    tick: int,
    daemon_id: str,
    superego_request_id: str,
) -> str:
    record = {
        "schema_version": "math_attempt_record_v1",
        "attempt_id": "",
        "problem_id": problem_id,
        "tick": int(tick),
        "daemon_id": daemon_id,
        "superego_request_id": superego_request_id,
        "objective_class": "BOUNDLESS_RESEARCH",
        "capabilities": ["FS_READ_WORKSPACE", "FS_WRITE_DAEMON_STATE", "SEALEDEXEC", "SUBPROCESS_TOOLCHAIN", "NETWORK_NONE"],
    }
    record["attempt_id"] = compute_attempt_id(record)
    return record["attempt_id"]


def _load_receipt_by_attempt(state_dir: Path, attempt_id: str) -> Tuple[dict[str, Any], str]:
    receipts_dir = state_dir / "math" / "attempts" / "receipts"
    for path in receipts_dir.glob("sha256_*.math_attempt_receipt_v1.json"):
        receipt = load_canon_json(path)
        if receipt.get("attempt_id") == attempt_id:
            receipt_hash = sha256_prefixed(canon_bytes(receipt))
            return receipt, receipt_hash
    _fail("ATTEMPT_RECEIPT_MISSING")
    return {}, ""


def run_attempt(
    *,
    problem_spec_path: Path,
    problems_dir: Path,
    policy_ir_path: Path,
    toolchain_manifest_path: Path,
    state_dir: Path,
    tick: int,
    daemon_id: str,
    superego_request_id: str,
    proof_token: str | None = None,
    lean_tactic: str | None = None,
) -> Tuple[dict[str, Any], str]:
    problem_spec = load_canon_json(problem_spec_path)
    if not isinstance(problem_spec, dict):
        _fail("PROBLEM_SPEC_INVALID")
    attempt_id = _build_attempt_id(
        problem_id=str(problem_spec.get("problem_id")),
        tick=tick,
        daemon_id=daemon_id,
        superego_request_id=superego_request_id,
    )

    cmd = [
        "python3",
        "-m",
        "cdel.v11_0.sealed_sas_math_attempt_worker_v1",
        "--problem-spec",
        str(problem_spec_path),
        "--problems-dir",
        str(problems_dir),
        "--policy-ir",
        str(policy_ir_path),
        "--toolchain-manifest",
        str(toolchain_manifest_path),
        "--attempt-id",
        attempt_id,
        "--tick",
        str(int(tick)),
        "--daemon-id",
        daemon_id,
        "--superego-request-id",
        superego_request_id,
        "--state-dir",
        str(state_dir),
    ]
    if proof_token is not None:
        cmd += ["--proof-token", proof_token]
    if lean_tactic is not None:
        cmd += ["--lean-tactic", lean_tactic]

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        _fail(f"SEALED_ATTEMPT_FAILED: {proc.stderr.strip()}")

    receipt, receipt_hash = _load_receipt_by_attempt(state_dir, attempt_id)
    return receipt, receipt_hash


__all__ = ["run_attempt", "SealedAttemptError"]
