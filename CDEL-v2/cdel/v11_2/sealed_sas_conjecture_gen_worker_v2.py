"""Sealed conjecture generation worker (v11.2)."""

from __future__ import annotations

import argparse
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from ..v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json
from ..v8_0.math_toolchain import compute_manifest_hash, load_toolchain_manifest
from ..v8_0.sealed_proofcheck import compute_sealed_receipt_hash
from .sas_conjecture_generator_v2 import generate_conjectures
from .sas_conjecture_ir_v2 import compute_conjecture_id, compute_fingerprint, compute_metrics, render_statement, validate_conjecture_ir
from .sas_conjecture_triviality_v2 import is_pattern_trivial, is_syntax_tautology, normalize_goal, novelty_gate_pass


def _limits_preexec(time_limit_ms: int, memory_limit_mb: int) -> Callable[[], None]:
    def _apply() -> None:
        try:
            import resource

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
    path = logs_dir / f"sha256_{digest.split(':',1)[1]}.{suffix}.log"
    path.write_bytes(data)
    return digest


def _run_lean_check(
    *,
    toolchain: dict[str, Any],
    work_dir: Path,
    proof_text: str,
    time_limit_ms: int,
    memory_limit_mb: int,
) -> dict[str, Any]:
    work_dir.mkdir(parents=True, exist_ok=True)
    entrypoint = "proof.lean"
    proof_path = work_dir / entrypoint
    proof_path.write_bytes(proof_text.encode("utf-8"))

    invocation = [
        str(arg).replace("{entrypoint}", entrypoint)
        for arg in list(toolchain.get("invocation_template") or [])
    ]
    env = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "PYTHONHASHSEED": "0"}

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

    return {
        "invocation": invocation,
        "env": env,
        "exit_code": exit_code,
        "result": result,
        "time_ms": elapsed_ms,
        "stdout": stdout,
        "stderr": stderr,
    }


def _proof_body(method: str) -> str:
    if method == "rfl":
        return "by\n  rfl\n"
    if method == "simp_core":
        return "by\n  simp\n"
    if method == "simp_algebra":
        return (
            "by\n"
            "  simp [\n"
            "    Nat.add_comm, Nat.add_left_comm, Nat.add_assoc,\n"
            "    Nat.mul_comm, Nat.mul_left_comm, Nat.mul_assoc,\n"
            "    Nat.mul_add, Nat.add_mul,\n"
            "    List.append_assoc, List.nil_append, List.append_nil,\n"
            "    List.length_append, List.length_map\n"
            "  ]\n"
        )
    if method == "one_lemma":
        return (
            "by\n"
            "  first\n"
            "  | exact Nat.add_comm _ _\n"
            "  | exact Nat.mul_comm _ _\n"
            "  | exact Nat.add_assoc _ _ _\n"
            "  | exact Nat.mul_assoc _ _ _\n"
            "  | exact List.append_assoc _ _ _\n"
            "  | exact List.append_nil _\n"
            "  | exact List.nil_append _\n"
            "  | exact List.length_append _ _\n"
            "  | exact List.length_map _ _\n"
            "  | exact Nat.dvd_refl _\n"
            "  | exact Nat.dvd_mul_of_dvd_left (by assumption) _\n"
            "  | exact Nat.dvd_mul_of_dvd_right (by assumption) _\n"
        )
    return "by\n  rfl\n"


def main() -> None:
    parser = argparse.ArgumentParser(prog="sealed_sas_conjecture_gen_worker_v2")
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--toolchain-manifest", required=True)
    parser.add_argument("--generator-seed", required=True)
    args = parser.parse_args()

    state_dir = Path(args.state_dir)
    cfg_path = Path(args.config)
    toolchain_path = Path(args.toolchain_manifest)

    config = load_canon_json(cfg_path)
    toolchain = load_toolchain_manifest(toolchain_path)
    toolchain_hash = compute_manifest_hash(toolchain)

    gen_seed = str(args.generator_seed)
    gen_cfg_hash = sha256_prefixed(canon_bytes(config))

    conjecture_dir = state_dir / "conjectures"
    ir_dir = conjecture_dir / "ir"
    bundles_dir = conjecture_dir / "bundles"
    receipts_dir = conjecture_dir / "receipts"
    sealed_dir = conjecture_dir / "sealed"
    logs_dir = conjecture_dir / "logs"
    work_dir = conjecture_dir / "work"
    sandbox_dir = conjecture_dir / "sandbox"
    for path in [ir_dir, bundles_dir, receipts_dir, sealed_dir, logs_dir, work_dir, sandbox_dir]:
        path.mkdir(parents=True, exist_ok=True)

    problems_dir = state_dir / "math" / "problems"
    problems_dir.mkdir(parents=True, exist_ok=True)

    time_limit_ms = int(config.get("time_limit_ms", 2000))
    memory_limit_mb = int(config.get("memory_limit_mb", 256))

    conjectures = generate_conjectures(seed_hash=gen_seed, config=config)
    bundle_conjectures = []

    for conj in conjectures:
        validate_conjecture_ir(conj)
        conjecture_id = compute_conjecture_id(conj)

        # Write IR
        ir_path = ir_dir / f"sha256_{conjecture_id.split(':',1)[1]}.sas_conjecture_ir_v2.json"
        write_canon_json(ir_path, conj)

        # Statement artifact
        statement_text = render_statement(conj)
        statement_bytes = (statement_text.strip() + "\n").encode("utf-8")
        statement_hash = sha256_prefixed(statement_bytes)
        statement_path = problems_dir / f"sha256_{statement_hash.split(':',1)[1]}.statement.txt"
        statement_path.write_bytes(statement_bytes)

        # Problem spec (Lean)
        spec = {
            "schema_version": "math_problem_spec_v1",
            "problem_id": statement_hash,
            "domain": "FORMAL_MATH",
            "difficulty_tier": "MEDIUM",
            "statement_artifact_hash": statement_hash,
            "checker_entrypoint": "proof.lean",
            "time_limit_ms": int(time_limit_ms),
            "memory_limit_mb": int(memory_limit_mb),
            "requires_library": True,
            "tags": ["sas_conjecture_gen_v2"],
        }
        spec_path = problems_dir / f"{statement_hash.split(':',1)[1]}.math_problem_spec_v1.json"
        write_canon_json(spec_path, spec)

        metrics = compute_metrics(conj)
        norm_goal = normalize_goal(conj.get("goal") or {})
        rejection_reason = ""
        triviality_checks: list[dict[str, Any]] = []

        if is_syntax_tautology(norm_goal):
            rejection_reason = "SYNTAX_TAUTOLOGY"
        elif is_pattern_trivial(norm_goal):
            rejection_reason = "PATTERN_TRIVIAL"
        else:
            any_pass = False
            for method in ["rfl", "simp_core", "simp_algebra", "one_lemma"]:
                proof_text = f"{statement_text}\n{_proof_body(method)}"
                check_work_dir = work_dir / conjecture_id / method
                result = _run_lean_check(
                    toolchain=toolchain,
                    work_dir=check_work_dir,
                    proof_text=proof_text,
                    time_limit_ms=time_limit_ms,
                    memory_limit_mb=memory_limit_mb,
                )
                stdout_hash = _write_log(logs_dir, suffix="stdout", data=result["stdout"])
                stderr_hash = _write_log(logs_dir, suffix="stderr", data=result["stderr"])

                sandbox_manifest = {
                    "network": "NONE",
                    "time_limit_ms": int(time_limit_ms),
                    "memory_limit_mb": int(memory_limit_mb),
                    "env": dict(result["env"]),
                }
                sandbox_manifest_hash = sha256_prefixed(canon_bytes(sandbox_manifest))
                sandbox_path = sandbox_dir / f"sha256_{sandbox_manifest_hash.split(':',1)[1]}.sandbox_manifest_v1.json"
                if not sandbox_path.exists():
                    write_canon_json(sandbox_path, sandbox_manifest)

                sealed_receipt = {
                    "schema_version": "sealed_proof_check_receipt_v1",
                    "toolchain_id": toolchain.get("toolchain_id"),
                    "problem_id": statement_hash,
                    "attempt_id": f"{conjecture_id}:{method}",
                    "invocation_argv": result["invocation"],
                    "exit_code": result["exit_code"],
                    "stdout_hash": stdout_hash,
                    "stderr_hash": stderr_hash,
                    "result": result["result"],
                    "time_ms": int(time_limit_ms),
                    "sandbox_manifest_hash": sandbox_manifest_hash,
                }
                sealed_hash = compute_sealed_receipt_hash(sealed_receipt)
                sealed_path = sealed_dir / f"sha256_{sealed_hash.split(':',1)[1]}.sealed_proof_check_receipt_v1.json"
                write_canon_json(sealed_path, sealed_receipt)

                triviality_checks.append(
                    {"method": method, "sealed_receipt_sha256": sealed_hash, "result": result["result"]}
                )
                if result["result"] == "PASS":
                    any_pass = True

            if any_pass:
                rejection_reason = "TRIVIAL_SOLVED"
            else:
                op_counts = metrics.get("op_counts") or {}
                if not novelty_gate_pass(op_counts):
                    rejection_reason = "NOVELTY_GATE_FAIL"

        fingerprint = compute_fingerprint(conj)
        fingerprint_hash = fingerprint.get("fingerprint_hash")
        status = "ACCEPTED" if rejection_reason == "" else "TRIVIAL_REJECTED"

        bundle_conjectures.append(
            {
                "conjecture_id": conjecture_id,
                "statement_hash": statement_hash,
                "fingerprint_hash": fingerprint_hash,
                "metrics": metrics,
                "triviality_checks": triviality_checks,
                "status": status,
                "rejection_reason": rejection_reason,
            }
        )

    bundle = {
        "schema_version": "sas_conjecture_bundle_v2",
        "bundle_id": "",
        "created_utc": "2026-02-05T00:00:00Z",
        "generator_seed": gen_seed,
        "generator_config_hash": gen_cfg_hash,
        "conjectures": bundle_conjectures,
    }
    bundle_hash = sha256_prefixed(canon_bytes({k: v for k, v in bundle.items() if k != "bundle_id"}))
    bundle["bundle_id"] = bundle_hash
    bundle_path = bundles_dir / f"sha256_{bundle_hash.split(':',1)[1]}.sas_conjecture_bundle_v2.json"
    write_canon_json(bundle_path, bundle)

    # Generator receipt
    stdout_hash = _write_log(logs_dir, suffix="stdout", data=b"")
    stderr_hash = _write_log(logs_dir, suffix="stderr", data=b"")
    receipt = {
        "schema_version": "sas_conjecture_gen_receipt_v2",
        "receipt_id": "",
        "created_utc": "2026-02-05T00:00:00Z",
        "generator_version": "sas_conjecture_gen_v2",
        "generator_config_hash": gen_cfg_hash,
        "generator_seed": gen_seed,
        "bundle_hash": bundle_hash,
        "toolchain_hash": toolchain_hash,
        "network_used": False,
        "stdout_hash": stdout_hash,
        "stderr_hash": stderr_hash,
    }
    receipt_hash = sha256_prefixed(canon_bytes({k: v for k, v in receipt.items() if k != "receipt_id"}))
    receipt["receipt_id"] = receipt_hash
    receipt_path = receipts_dir / f"sha256_{receipt_hash.split(':',1)[1]}.sas_conjecture_gen_receipt_v2.json"
    write_canon_json(receipt_path, receipt)


if __name__ == "__main__":
    main()
