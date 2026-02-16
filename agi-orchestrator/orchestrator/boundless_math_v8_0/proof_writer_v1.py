"""Proof artifact writer (v8.0)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Tuple


def _render_proof(statement_text: str) -> str:
    stripped = statement_text.strip()
    if not stripped:
        raise ValueError("empty statement")
    if "{{PROOF}}" in statement_text:
        return statement_text.replace("{{PROOF}}", "by rfl")
    if stripped.endswith(":="):
        return f"{stripped} by rfl"
    if stripped.endswith(":= by rfl") or "by rfl" in stripped:
        return stripped
    return f"{stripped}\nby rfl"


def write_proof(
    *,
    proofs_dir: Path,
    attempt_dir: Path,
    problems_dir: Path,
    attempt_id: str,
    problem_spec: dict[str, Any],
) -> Tuple[Path, str]:
    proofs_dir.mkdir(parents=True, exist_ok=True)
    attempt_dir.mkdir(parents=True, exist_ok=True)

    statement_hash = str(problem_spec.get("statement_artifact_hash") or "")
    if not statement_hash.startswith("sha256:"):
        raise ValueError("missing statement_artifact_hash")
    statement_name = f"sha256_{statement_hash.split(':',1)[1]}.statement.txt"
    statement_src = problems_dir / statement_name
    if not statement_src.exists():
        raise FileNotFoundError(f"statement missing: {statement_src}")

    statement_text = statement_src.read_text(encoding="utf-8")
    statement_dst = attempt_dir / "statement.txt"
    statement_dst.write_text(statement_text, encoding="utf-8")

    proof_text = _render_proof(statement_text)
    content = (proof_text.strip() + "\n").encode("utf-8")
    proof_hash = "sha256:" + hashlib.sha256(content).hexdigest()

    entrypoint = str(problem_spec.get("checker_entrypoint") or "proof.lean")
    proof_path = attempt_dir / entrypoint
    proof_path.write_bytes(content)

    artifact_path = proofs_dir / f"sha256_{proof_hash.split(':',1)[1]}.proof.lean"
    artifact_path.write_bytes(content)
    return proof_path, proof_hash


__all__ = ["write_proof"]
