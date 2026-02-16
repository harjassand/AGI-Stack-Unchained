from __future__ import annotations

from pathlib import Path

from cdel.v15_0.verify_rsi_sas_kernel_v1 import _scan_rust_structure

from .utils import repo_root


def test_forbid_unsafe_and_tokens() -> None:
    root = repo_root()
    _scan_rust_structure(root / "CDEL-v2" / "cdel" / "v15_0" / "rust" / "agi_kernel_rs_v1" / "src")
