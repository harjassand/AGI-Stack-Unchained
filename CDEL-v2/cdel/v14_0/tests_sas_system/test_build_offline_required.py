from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v14_0.sas_system_build_v1 import SASSystemBuildError, sealed_rust_build_receipt


def test_build_requires_offline_flag(tmp_path: Path) -> None:
    manifest = {
        "toolchain_id": "sha256:" + "0" * 64,
        "invocation_template": ["/usr/bin/cargo", "build", "--release", "--locked", "--manifest-path", "{entrypoint}"],
    }
    with pytest.raises(SASSystemBuildError) as exc:
        sealed_rust_build_receipt(
            toolchain_manifest=manifest,
            crate_dir=tmp_path,
            problem_id="p",
            attempt_id="a",
        )
    assert "INVALID:RUST_BUILD_NOT_OFFLINE" in str(exc.value)
