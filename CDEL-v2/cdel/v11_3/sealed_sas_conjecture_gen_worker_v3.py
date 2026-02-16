"""Sealed conjecture generation worker (v11.3)."""

from __future__ import annotations

import argparse
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from ..v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json
from ..v8_0.math_toolchain import compute_manifest_hash, load_toolchain_manifest
from ..v8_0.sealed_proofcheck import compute_sealed_receipt_hash
from .sas_conjecture_generator_v3 import generate_conjectures
from .sas_conjecture_ir_v3 import (
    compute_fingerprint_hash,
    compute_metrics,
    collect_used_binders,
    render_statement,
    validate_conjecture_ir,
)
from .sas_conjecture_triviality_v3 import is_syntax_tautology, normalize_goal


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


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
    if method == "simp_preamble":
        return (
            "by\n"
            "  simp [lappend, llen, lsum, lrev, lmap, range, lsorted, linsert, lsort]\n"
        )
    return "by\n  rfl\n"


def _strip_lean_comments(text: str) -> str:
    # Remove block comments and line comments to avoid rejecting preamble docstrings.
    text = re.sub(r"/-.*?-/", "", text, flags=re.S)
    text = re.sub(r"--.*", "", text)
    return text


def _contains_forbidden(text: str, tokens: list[str]) -> bool:
    stripped = _strip_lean_comments(text)
    for token in tokens:
        if token and token in stripped:
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(prog="sealed_sas_conjecture_gen_worker_v3")
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

    preamble_rel = str(config.get("preamble_relpath") or "")
    preamble_path = Path(preamble_rel)
    if not preamble_path.is_absolute():
        preamble_path = _repo_root() / preamble_path
    preamble_text = preamble_path.read_text(encoding="utf-8")

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

    time_limit_ms = int(config.get("time_limit_ms", 4000))
    memory_limit_mb = int(config.get("memory_limit_mb", 256))
    trivial_time_ms = 250
    trivial_mem_mb = 256

    forbidden_tokens = list(config.get("forbidden_tokens_statement") or [])

    conjectures = generate_conjectures(seed_hash=gen_seed, config=config)
    bundle_conjectures = []
    seen_fingerprints: set[str] = set()

    for conj in conjectures:
        validate_conjecture_ir(conj)
        fingerprint_hash = str(conj.get("fingerprint_hash"))
        if fingerprint_hash in seen_fingerprints:
            continue
        seen_fingerprints.add(fingerprint_hash)
        conjecture_id = fingerprint_hash

        # Write IR
        ir_path = ir_dir / f"sha256_{conjecture_id.split(':',1)[1]}.sas_conjecture_ir_v3.json"
        write_canon_json(ir_path, conj)

        # Statement artifact
        statement_text = render_statement(conj, preamble_text=preamble_text)
        statement_bytes = (statement_text.rstrip("\n") + "\n").encode("utf-8")
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
            "tags": ["sas_conjecture_gen_v3"],
        }
        spec_path = problems_dir / f"{statement_hash.split(':',1)[1]}.math_problem_spec_v1.json"
        write_canon_json(spec_path, spec)

        metrics = compute_metrics(conj)
        norm_goal = normalize_goal(conj.get("goal") or {})
        rejection_reason = ""
        triviality_checks: list[dict[str, Any]] = []

        # Relevance gate
        used = collect_used_binders(conj.get("goal") or {})
        declared = {v.get("name") for v in (conj.get("vars") or []) if isinstance(v, dict)}
        if not declared.issubset(used):
            rejection_reason = "UNUSED_BINDER"

        # Recursive-focus gate
        if not rejection_reason:
            if not metrics.get("has_lnat") or not metrics.get("has_rec_op"):
                rejection_reason = "NO_RECURSIVE_STRUCTURE"

        # Layer A: syntactic tautology
        if not rejection_reason and is_syntax_tautology(norm_goal):
            rejection_reason = "SYNTAX_TAUTOLOGY"

        # Layer C: forbidden token scan
        if not rejection_reason and _contains_forbidden(statement_text, forbidden_tokens):
            rejection_reason = "FORBIDDEN_TOKEN_STATEMENT"

        # Layer B: definitional triviality probes
        if not rejection_reason:
            any_pass = False
            for method in ["rfl", "simp_preamble"]:
                proof_text = f"{statement_text}\n{_proof_body(method)}"
                check_work_dir = work_dir / conjecture_id / method
                result = _run_lean_check(
                    toolchain=toolchain,
                    work_dir=check_work_dir,
                    proof_text=proof_text,
                    time_limit_ms=trivial_time_ms,
                    memory_limit_mb=trivial_mem_mb,
                )
                stdout_hash = _write_log(logs_dir, suffix="stdout", data=result["stdout"])
                stderr_hash = _write_log(logs_dir, suffix="stderr", data=result["stderr"])

                sandbox_manifest = {
                    "network": "NONE",
                    "time_limit_ms": int(trivial_time_ms),
                    "memory_limit_mb": int(trivial_mem_mb),
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
                    "time_ms": int(trivial_time_ms),
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
                passed = next((c for c in triviality_checks if c.get("result") == "PASS"), None)
                method = passed.get("method") if isinstance(passed, dict) else "rfl"
                rejection_reason = f"TRIVIAL_SOLVED_{method}"

        status = "CANDIDATE" if rejection_reason == "" else "TRIVIAL_REJECTED"

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
        "schema_version": "sas_conjecture_bundle_v3",
        "bundle_id": "",
        "created_utc": "2026-02-05T00:00:00Z",
        "generator_seed": gen_seed,
        "generator_config_hash": gen_cfg_hash,
        "conjectures": bundle_conjectures,
    }
    bundle_hash = sha256_prefixed(canon_bytes({k: v for k, v in bundle.items() if k != "bundle_id"}))
    bundle["bundle_id"] = bundle_hash
    bundle_path = bundles_dir / f"sha256_{bundle_hash.split(':',1)[1]}.sas_conjecture_bundle_v3.json"
    write_canon_json(bundle_path, bundle)

    # Generator receipt
    stdout_hash = _write_log(logs_dir, suffix="stdout", data=b"")
    stderr_hash = _write_log(logs_dir, suffix="stderr", data=b"")
    receipt = {
        "schema_version": "sas_conjecture_gen_receipt_v3",
        "receipt_id": "",
        "created_utc": "2026-02-05T00:00:00Z",
        "generator_version": "sas_conjecture_gen_v3",
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
    receipt_path = receipts_dir / f"sha256_{receipt_hash.split(':',1)[1]}.sas_conjecture_gen_receipt_v3.json"
    write_canon_json(receipt_path, receipt)


if __name__ == "__main__":
    main()
