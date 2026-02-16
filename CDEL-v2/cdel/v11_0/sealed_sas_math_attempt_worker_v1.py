"""Sealed SAS-MATH attempt worker (v11.0)."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from ..v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json
from ..v8_0.math_attempts import compute_attempt_id, compute_attempt_receipt_hash
from ..v8_0.math_toolchain import compute_manifest_hash, load_toolchain_manifest
from ..v8_0.sealed_proofcheck import compute_sealed_receipt_hash
from .sas_math_policy_ir_v1 import compute_policy_id


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
    digest = sha256_prefixed(data)
    name = f"sha256_{digest.split(':',1)[1]}.{suffix}.log"
    path = logs_dir / name
    path.write_bytes(data)
    return digest


def _load_statement(problems_dir: Path, statement_hash: str) -> tuple[Path, bytes]:
    if not statement_hash.startswith("sha256:"):
        raise SystemExit("invalid statement hash")
    name = f"sha256_{statement_hash.split(':',1)[1]}.statement.txt"
    path = problems_dir / name
    if not path.exists():
        raise SystemExit("statement missing")
    return path, path.read_bytes()


def _write_proof_toy(
    *,
    work_dir: Path,
    entrypoint: str,
    attempt_id: str,
    problem_id: str,
    statement_hash: str,
    proof_token: str,
) -> tuple[Path, bytes]:
    proof_obj = {
        "schema_version": "math_proof_v1",
        "attempt_id": attempt_id,
        "problem_id": problem_id,
        "statement_hash": statement_hash,
        "proof": proof_token,
    }
    content = json.dumps(proof_obj, separators=(",", ":"), sort_keys=True).encode("utf-8")
    proof_path = work_dir / entrypoint
    proof_path.write_bytes(content)
    return proof_path, content


def _write_proof_lean(*, work_dir: Path, entrypoint: str, statement_text: str, tactic: str) -> tuple[Path, bytes]:
    stripped = statement_text.strip()
    if stripped.endswith(":="):
        proof_text = f"{stripped} by {tactic}\n"
    elif "by" in stripped:
        proof_text = stripped + "\n"
    else:
        proof_text = f"{stripped}\nby {tactic}\n"
    content = proof_text.encode("utf-8")
    proof_path = work_dir / entrypoint
    proof_path.write_bytes(content)
    return proof_path, content


def main() -> None:
    parser = argparse.ArgumentParser(prog="sealed_sas_math_attempt_worker_v1")
    parser.add_argument("--problem-spec", required=True)
    parser.add_argument("--problems-dir", required=True)
    parser.add_argument("--policy-ir", required=True)
    parser.add_argument("--toolchain-manifest", required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--tick", required=True, type=int)
    parser.add_argument("--daemon-id", required=True)
    parser.add_argument("--superego-request-id", required=True)
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--proof-token")
    parser.add_argument("--lean-tactic")
    args = parser.parse_args()

    state_dir = Path(args.state_dir)
    math_root = state_dir / "math"
    problems_dir = Path(args.problems_dir)

    problem_spec = load_canon_json(Path(args.problem_spec))
    if not isinstance(problem_spec, dict) or problem_spec.get("schema_version") != "math_problem_spec_v1":
        raise SystemExit("invalid problem spec")

    policy_ir = load_canon_json(Path(args.policy_ir))
    if not isinstance(policy_ir, dict) or policy_ir.get("schema_version") != "sas_math_policy_ir_v1":
        raise SystemExit("invalid policy ir")
    policy_id = compute_policy_id(policy_ir)
    if policy_ir.get("policy_id") != policy_id:
        raise SystemExit("policy id mismatch")

    toolchain = load_toolchain_manifest(Path(args.toolchain_manifest))
    toolchain_manifest_hash = compute_manifest_hash(toolchain)

    problem_id = str(problem_spec.get("problem_id"))
    statement_hash = str(problem_spec.get("statement_artifact_hash"))
    entrypoint = str(problem_spec.get("checker_entrypoint"))
    time_limit_ms = int(problem_spec.get("time_limit_ms", 1000))
    memory_limit_mb = int(problem_spec.get("memory_limit_mb", 256))

    statement_path, statement_bytes = _load_statement(problems_dir, statement_hash)

    work_dir = math_root / "work" / "attempts" / args.attempt_id
    work_dir.mkdir(parents=True, exist_ok=True)

    # Copy statement into work dir
    (work_dir / "statement.txt").write_bytes(statement_bytes)

    checker_name = str(toolchain.get("checker_name", ""))
    proof_bytes: bytes
    proof_path: Path
    if checker_name == "toy_kernel" or policy_ir.get("policy_family") in {"toy_checker_proof_v1", "mixed_v1"}:
        proof_token = args.proof_token or ""
        if not proof_token:
            raise SystemExit("missing proof token")
        proof_path, proof_bytes = _write_proof_toy(
            work_dir=work_dir,
            entrypoint=entrypoint,
            attempt_id=args.attempt_id,
            problem_id=problem_id,
            statement_hash=statement_hash,
            proof_token=proof_token,
        )
        proof_artifact_path = math_root / "attempts" / "proofs" / f"sha256_{sha256_prefixed(proof_bytes).split(':',1)[1]}.proof"
    else:
        tactic = args.lean_tactic or "rfl"
        proof_path, proof_bytes = _write_proof_lean(
            work_dir=work_dir,
            entrypoint=entrypoint,
            statement_text=statement_bytes.decode("utf-8"),
            tactic=tactic,
        )
        proof_artifact_path = math_root / "attempts" / "proofs" / f"sha256_{sha256_prefixed(proof_bytes).split(':',1)[1]}.proof.lean"

    proof_artifact_path.parent.mkdir(parents=True, exist_ok=True)
    proof_artifact_path.write_bytes(proof_bytes)
    proof_artifact_hash = sha256_prefixed(proof_bytes)

    # Attempt record (enforces NETWORK_NONE via schema)
    capabilities = ["FS_READ_WORKSPACE", "FS_WRITE_DAEMON_STATE", "SEALEDEXEC", "SUBPROCESS_TOOLCHAIN", "NETWORK_NONE"]
    attempt_record = {
        "schema_version": "math_attempt_record_v1",
        "attempt_id": "",
        "problem_id": problem_id,
        "tick": int(args.tick),
        "daemon_id": args.daemon_id,
        "superego_request_id": args.superego_request_id,
        "objective_class": "BOUNDLESS_RESEARCH",
        "capabilities": capabilities,
    }
    attempt_record["attempt_id"] = compute_attempt_id(attempt_record)
    if attempt_record["attempt_id"] != args.attempt_id:
        raise SystemExit("attempt id mismatch")
    record_hash = sha256_prefixed(canon_bytes(attempt_record))
    record_path = math_root / "attempts" / "records" / f"sha256_{record_hash.split(':',1)[1]}.math_attempt_record_v1.json"
    record_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(record_path, attempt_record)

    invocation = [str(arg).replace("{entrypoint}", str(proof_path)) for arg in list(toolchain.get("invocation_template") or [])]
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
            cwd=str(work_dir),
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
    logs_dir = math_root / "attempts" / "logs"
    stdout_hash = _write_log(logs_dir, suffix="stdout", data=stdout)
    stderr_hash = _write_log(logs_dir, suffix="stderr", data=stderr)

    sandbox_manifest = {
        "network": "NONE",
        "time_limit_ms": int(time_limit_ms),
        "memory_limit_mb": int(memory_limit_mb),
        "env": dict(env),
    }
    sandbox_manifest_hash = sha256_prefixed(canon_bytes(sandbox_manifest))

    sealed_receipt = {
        "schema_version": "sealed_proof_check_receipt_v1",
        "toolchain_id": toolchain.get("toolchain_id"),
        "problem_id": problem_id,
        "attempt_id": args.attempt_id,
        "invocation_argv": invocation,
        "exit_code": exit_code,
        "stdout_hash": stdout_hash,
        "stderr_hash": stderr_hash,
        "result": result,
        "time_ms": elapsed_ms,
        "sandbox_manifest_hash": sandbox_manifest_hash,
    }
    sealed_hash = compute_sealed_receipt_hash(sealed_receipt)
    sealed_path = math_root / "attempts" / "sealed" / f"sha256_{sealed_hash.split(':',1)[1]}.sealed_proof_check_receipt_v1.json"
    sealed_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(sealed_path, sealed_receipt)

    attempt_receipt = {
        "schema_version": "math_attempt_receipt_v1",
        "attempt_id": args.attempt_id,
        "problem_id": problem_id,
        "tick": int(args.tick),
        "daemon_id": args.daemon_id,
        "toolchain_id": toolchain.get("toolchain_id"),
        "toolchain_manifest_hash": toolchain_manifest_hash,
        "sealed_proof_check_receipt_hash": sealed_hash,
        "result": result,
        "proof_artifact_hash": proof_artifact_hash,
        "stdout_hash": stdout_hash,
        "stderr_hash": stderr_hash,
        "wall_ms": int(elapsed_ms),
    }
    receipt_hash = compute_attempt_receipt_hash(attempt_receipt)
    receipt_path = math_root / "attempts" / "receipts" / f"sha256_{receipt_hash.split(':',1)[1]}.math_attempt_receipt_v1.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(receipt_path, attempt_receipt)


if __name__ == "__main__":
    main()
