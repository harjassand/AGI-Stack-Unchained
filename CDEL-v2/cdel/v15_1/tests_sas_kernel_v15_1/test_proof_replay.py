from __future__ import annotations

from cdel.v15_1.verify_rsi_sas_kernel_v15_1 import _scan_lean_forbidden

from .utils import repo_root


def test_proof_replay_tokens() -> None:
    root = repo_root()
    _scan_lean_forbidden(
        root / "CDEL-v2" / "cdel" / "v15_1" / "lean" / "KernelBrainSafetyV15_1.lean",
        require_non_vacuous=True,
    )
