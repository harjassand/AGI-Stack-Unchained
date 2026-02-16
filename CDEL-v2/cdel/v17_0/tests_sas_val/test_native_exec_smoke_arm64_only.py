from __future__ import annotations

import platform
from pathlib import Path

import pytest

from cdel.v1_7r.canon import load_canon_json
from cdel.v17_0.verify_rsi_sas_val_v1 import verify


@pytest.mark.skipif(platform.machine() != "arm64", reason="native AArch64 test")
def test_native_exec_smoke_arm64_only(v17_state_dir: Path) -> None:
    baseline_backend = load_canon_json(v17_state_dir / "baseline" / "exec" / "val_exec_backend_v1.json")
    candidate_backend = load_canon_json(v17_state_dir / "candidate" / "exec" / "val_exec_backend_v1.json")
    assert candidate_backend["exec_backend"] == "RUST_NATIVE_AARCH64_MMAP_RX_V1"
    assert baseline_backend["output_hash"] == candidate_backend["output_hash"]
    assert verify(v17_state_dir, mode="full") == "VALID"
