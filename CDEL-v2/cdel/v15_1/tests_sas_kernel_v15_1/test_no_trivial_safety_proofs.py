from __future__ import annotations

import re

from cdel.v15_1.verify_rsi_sas_kernel_v15_1 import _scan_lean_forbidden

from .utils import repo_root


def test_no_trivial_safety_proofs() -> None:
    root = repo_root()
    proof_path = root / "CDEL-v2" / "cdel" / "v15_1" / "lean" / "KernelBrainSafetyV15_1.lean"
    text = proof_path.read_text(encoding="utf-8")

    assert not re.search(r":\s*True\b", text)
    assert not re.search(r"\bby\s+trivial\b", text)

    _scan_lean_forbidden(proof_path, require_non_vacuous=True)
