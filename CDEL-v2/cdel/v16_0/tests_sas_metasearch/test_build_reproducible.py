from __future__ import annotations

from pathlib import Path

from cdel.v16_0.metasearch_build_rust_v1 import build_release_binary, file_hash, load_rust_toolchain_manifest


def test_build_reproducible() -> None:
    crate = Path("CDEL-v2/cdel/v16_0/rust/sas_metasearch_rs_v1")
    tool = load_rust_toolchain_manifest(Path("daemon/rsi_sas_metasearch_v16_0/config/toolchain_manifest_rust_v1.json"))
    bin1 = build_release_binary(crate_dir=crate, rust_toolchain=tool)
    h1 = file_hash(bin1)
    bin2 = build_release_binary(crate_dir=crate, rust_toolchain=tool)
    h2 = file_hash(bin2)
    assert h1 == h2
