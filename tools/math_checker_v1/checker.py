#!/usr/bin/env python3
"""Deterministic math proof checker (toy kernel v1).

This checker validates a minimal proof format:
  - A statement file named "statement.txt" exists next to the proof file.
  - The proof file is JSON with:
      {"schema_version":"math_proof_v1","statement_hash":"sha256:...","proof":"refl"}
  - The statement hash matches the content hash of statement.txt.
  - The statement is of the form "X = X" (token equality).
  - The proof is exactly "refl".

Exit code 0 = PASS, non-zero = FAIL.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def _sha256_prefixed(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _fail(msg: str, code: int = 1) -> int:
    print(f"FAIL: {msg}", file=sys.stderr)
    return code


def _parse_statement(text: str) -> tuple[str, str] | None:
    if "=" not in text:
        return None
    left, right = text.split("=", 1)
    left = left.strip()
    right = right.strip()
    if not left or not right:
        return None
    return left, right


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        return _fail("usage: checker.py <proof_entrypoint>", 2)

    proof_path = Path(argv[1])
    if not proof_path.exists():
        return _fail("proof entrypoint missing", 2)

    statement_path = proof_path.parent / "statement.txt"
    if not statement_path.exists():
        return _fail("statement.txt missing", 3)

    try:
        proof = json.loads(proof_path.read_text(encoding="utf-8"))
    except Exception:
        return _fail("proof JSON invalid", 4)

    if not isinstance(proof, dict) or proof.get("schema_version") != "math_proof_v1":
        return _fail("proof schema invalid", 5)

    statement_hash = proof.get("statement_hash")
    if not isinstance(statement_hash, str):
        return _fail("statement_hash missing", 6)

    statement_bytes = statement_path.read_bytes()
    expected_hash = _sha256_prefixed(statement_bytes)
    if expected_hash != statement_hash:
        return _fail("statement hash mismatch", 7)

    statement_text = statement_bytes.decode("utf-8").strip()
    parsed = _parse_statement(statement_text)
    if parsed is None:
        return _fail("statement not in X = X form", 8)
    left, right = parsed
    if left != right:
        return _fail("statement not reflexive", 9)

    if proof.get("proof") != "refl":
        return _fail("proof not refl", 10)

    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
