from __future__ import annotations

from pathlib import Path

from cdel.v16_1.metasearch_build_rust_v1 import crate_tree_hash, file_hash
from cdel.v16_1.verify_rsi_sas_metasearch_v16_1 import _resolve_rust_binary_for_planner


def test_verifier_skip_rebuild_fastpath(tmp_path, monkeypatch) -> None:
    crate = tmp_path / "crate"
    (crate / "src").mkdir(parents=True, exist_ok=True)
    (crate / "src" / "main.rs").write_text("fn main() {}\n", encoding="utf-8")
    binary = crate / "target" / "release" / "sas_metasearch_rs_v1"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_bytes(b"fastpath-binary")

    expected_crate_hash = crate_tree_hash(crate)
    expected_bin_hash = file_hash(binary)

    def _raise_if_called(*, crate_dir: Path, rust_toolchain: dict[str, str]):
        raise AssertionError("build_release_binary_with_receipt should not be called in fast path")

    monkeypatch.setattr(
        "cdel.v16_1.verify_rsi_sas_metasearch_v16_1.build_release_binary_with_receipt",
        _raise_if_called,
    )

    resolved_binary, rebuilt_receipt = _resolve_rust_binary_for_planner(
        crate_dir=crate,
        rust_toolchain={},
        expected_crate_hash=expected_crate_hash,
        expected_bin_hash=expected_bin_hash,
    )

    assert resolved_binary == binary
    assert rebuilt_receipt is None
