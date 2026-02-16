from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v16_1.tests_sas_metasearch.utils import copy_run, daemon_state
from cdel.v16_1.verify_rsi_sas_metasearch_v16_1 import MetaSearchVerifyError, verify


def test_rust_binary_pinning(v16_1_run_root: Path, tmp_path: Path) -> None:
    run_root = copy_run(v16_1_run_root, tmp_path / "run_bin_tamper")
    state = daemon_state(run_root)

    binary = Path("CDEL-v2/cdel/v16_1/rust/sas_metasearch_rs_v1/target/release/sas_metasearch_rs_v1")
    if not binary.exists():
        pytest.skip("binary not built in this environment")

    original = binary.read_bytes()
    n = min(1024, len(original))
    binary.write_bytes((b"X" * n) + original[n:])
    try:
        with pytest.raises(MetaSearchVerifyError) as exc:
            verify(state, mode="full")
        assert str(exc.value) == "INVALID:BIN_HASH_MISMATCH"
    finally:
        binary.write_bytes(original)
