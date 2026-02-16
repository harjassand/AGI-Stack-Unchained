"""Boundless math tick controller (v8.0)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Tuple

from cdel.v1_7r.canon import canon_bytes, write_canon_json
from cdel.v8_0.math_attempts import compute_attempt_receipt_hash
from cdel.v8_0.math_toolchain import compute_manifest_hash

from .attempt_builder_v1 import build_attempt_record
from .budget_v1 import MathBudget
from .ledger_writer_v1 import MathLedgerWriter
from .problem_selector_v1 import select_problem
from .proof_writer_v1 import write_proof
from .sealed_check_client_v1 import run_sealed_check
from .solved_index_v1 import update_solved_index


class BoundlessMathError(RuntimeError):
    pass


def _sha256_prefixed(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _checker_hash_matches(manifest: dict[str, Any]) -> bool:
    expected = str(manifest.get("checker_executable_hash") or "")
    if not expected.startswith("sha256:"):
        return False
    invocation = list(manifest.get("invocation_template") or [])
    for arg in invocation:
        if not isinstance(arg, str):
            continue
        if "{entrypoint}" in arg:
            continue
        path = Path(arg)
        if not (path.exists() and path.is_file()):
            continue
        actual = _sha256_prefixed(path.read_bytes())
        if actual == expected:
            return True
    return False


def run_tick(
    *,
    tick: int,
    daemon_id: str,
    state_dir: Path,
    math_pack: dict[str, Any],
    toolchain_manifest: dict[str, Any],
    superego_request_id: str,
    capabilities: list[str],
    budget: MathBudget,
    daemon_ledger_writer: Any,
) -> Tuple[str, Path, dict[str, Any]]:
    math_root = state_dir / "math"
    problems_dir = Path(str(math_pack.get("problems_dir")))
    selection_policy = str(math_pack.get("selection_policy", "first"))

    problem_spec, problem_path = select_problem(problems_dir, policy=selection_policy)
    (math_root / "work").mkdir(parents=True, exist_ok=True)
    write_canon_json(math_root / "work" / "current_problem.json", problem_spec)

    state_problems_dir = math_root / "problems"
    state_problems_dir.mkdir(parents=True, exist_ok=True)
    state_problem_path = state_problems_dir / problem_path.name
    if not state_problem_path.exists():
        state_problem_path.write_bytes(problem_path.read_bytes())
    statement_hash = str(problem_spec.get("statement_artifact_hash") or "")
    if statement_hash.startswith("sha256:"):
        statement_name = f"sha256_{statement_hash.split(':',1)[1]}.statement.txt"
        statement_src = problems_dir / statement_name
        statement_dst = state_problems_dir / statement_name
        if statement_src.exists() and not statement_dst.exists():
            statement_dst.write_bytes(statement_src.read_bytes())

    if not budget.can_attempt(0):
        raise BoundlessMathError("BOUNDLESS_MATH_BUDGET_EXCEEDED")
    if not _checker_hash_matches(toolchain_manifest):
        raise BoundlessMathError("BOUNDLESS_MATH_TOOLCHAIN_DRIFT")

    record = build_attempt_record(
        daemon_id=daemon_id,
        tick=tick,
        problem_id=str(problem_spec.get("problem_id")),
        superego_request_id=superego_request_id,
        capabilities=capabilities,
    )
    attempt_id = record["attempt_id"]

    attempt_dir = math_root / "work" / "attempts" / attempt_id

    record_hash = _sha256_prefixed(canon_bytes(record))
    record_path = math_root / "attempts" / "records" / f"sha256_{record_hash.split(':',1)[1]}.math_attempt_record_v1.json"
    write_canon_json(record_path, record)

    ledger = MathLedgerWriter(math_root / "ledger" / "math_research_ledger_v1.jsonl")
    if (math_root / "ledger" / "math_research_ledger_v1.jsonl").read_text(encoding="utf-8").strip() == "":
        ledger.append(event_type="MATH_BOOTSTRAP", event_payload={"note": "bootstrap"}, tick=0)

    ledger.append(event_type="PROBLEM_SELECTED", event_payload={"problem_id": problem_spec.get("problem_id")}, tick=tick)
    ledger.append(event_type="ATTEMPT_STARTED", event_payload={"attempt_id": attempt_id}, tick=tick)

    daemon_ledger_writer.append(
        event_type="MATH_ATTEMPT_STARTED",
        event_payload={"attempt_id": attempt_id, "request_id": superego_request_id, "problem_id": problem_spec.get("problem_id")},
        tick=tick,
    )

    proofs_dir = math_root / "attempts" / "proofs"
    proof_path, proof_hash = write_proof(
        proofs_dir=proofs_dir,
        attempt_dir=attempt_dir,
        problems_dir=problems_dir,
        attempt_id=attempt_id,
        problem_spec=problem_spec,
    )

    ledger.append(event_type="SEALED_PROOF_CHECK_STARTED", event_payload={"attempt_id": attempt_id}, tick=tick)

    sealed_dir = math_root / "attempts" / "sealed"
    logs_dir = math_root / "attempts" / "logs"
    sealed_receipt, sealed_hash = run_sealed_check(
        sealed_dir=sealed_dir,
        logs_dir=logs_dir,
        toolchain_manifest=toolchain_manifest,
        attempt_id=attempt_id,
        problem_id=str(problem_spec.get("problem_id")),
        entrypoint=str(proof_path),
        proof_path=proof_path,
        time_limit_ms=int(problem_spec.get("time_limit_ms", 1000)),
        memory_limit_mb=int(problem_spec.get("memory_limit_mb", 256)),
    )

    daemon_ledger_writer.append(
        event_type="SEALED_PROOF_CHECK",
        event_payload={"attempt_id": attempt_id, "sealed_receipt_hash": sealed_hash},
        tick=tick,
    )

    ledger.append(
        event_type="SEALED_PROOF_CHECK_RESULT",
        event_payload={"attempt_id": attempt_id, "result": sealed_receipt.get("result")},
        tick=tick,
    )

    toolchain_manifest_hash = compute_manifest_hash(toolchain_manifest)

    attempt_receipt = {
        "schema_version": "math_attempt_receipt_v1",
        "attempt_id": attempt_id,
        "problem_id": problem_spec.get("problem_id"),
        "tick": int(tick),
        "daemon_id": daemon_id,
        "toolchain_id": toolchain_manifest.get("toolchain_id"),
        "toolchain_manifest_hash": toolchain_manifest_hash,
        "sealed_proof_check_receipt_hash": sealed_hash,
        "result": sealed_receipt.get("result"),
        "proof_artifact_hash": proof_hash,
        "stdout_hash": sealed_receipt.get("stdout_hash"),
        "stderr_hash": sealed_receipt.get("stderr_hash"),
        "wall_ms": int(sealed_receipt.get("time_ms", 0)),
    }
    attempt_receipt_hash = compute_attempt_receipt_hash(attempt_receipt)
    receipt_path = math_root / "attempts" / "receipts" / f"sha256_{attempt_receipt_hash.split(':',1)[1]}.math_attempt_receipt_v1.json"
    write_canon_json(receipt_path, attempt_receipt)

    ledger.append(event_type="ATTEMPT_RESULT_RECORDED", event_payload={"attempt_id": attempt_id}, tick=tick)

    daemon_ledger_writer.append(
        event_type="MATH_ATTEMPT_RESULT",
        event_payload={"attempt_id": attempt_id, "result": sealed_receipt.get("result")},
        tick=tick,
    )

    if sealed_receipt.get("result") == "PASS":
        solution = {
            "schema_version": "math_solution_receipt_v1",
            "attempt_id": attempt_id,
            "problem_id": problem_spec.get("problem_id"),
            "tick": int(tick),
            "daemon_id": daemon_id,
            "toolchain_manifest_hash": toolchain_manifest_hash,
            "sealed_proof_check_receipt_hash": sealed_hash,
            "proof_artifact_hash": proof_hash,
            "created_utc": "",
        }
        solution_hash = _sha256_prefixed(canon_bytes(solution))
        solution_path = math_root / "solved" / "receipts" / f"sha256_{solution_hash.split(':',1)[1]}.math_solution_receipt_v1.json"
        write_canon_json(solution_path, solution)
        update_solved_index(
            math_root / "solved" / "solved_index_v1.json",
            problem_id=str(problem_spec.get("problem_id")),
            attempt_id=attempt_id,
            proof_artifact_hash=proof_hash,
            receipt_hash=solution_hash,
        )
        ledger.append(event_type="PROOF_ACCEPTED", event_payload={"attempt_id": attempt_id}, tick=tick)
    else:
        ledger.append(event_type="PROOF_REJECTED", event_payload={"attempt_id": attempt_id}, tick=tick)

    ledger.append(event_type="SOLVED_INDEX_UPDATED", event_payload={"count": 1}, tick=tick)

    budget.record_attempt()

    return attempt_receipt_hash, receipt_path, attempt_receipt


__all__ = ["run_tick", "BoundlessMathError"]
