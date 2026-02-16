from __future__ import annotations

import json
from pathlib import Path

import pytest

from cdel.v14_0.sas_system_build_v1 import SASSystemBuildError, require_vendor


_KNOWN_HASH = "47865a6fa77ecfc7fff126c06bb04a95a0c996f04b628d6ece7e059b9f68731f"
_KNOWN_BYTES = b"build/lib.linux-x86_64-3.11"


def _write_checksum(crate_dir: Path, expected_hash: str) -> None:
    checksum = {
        "files": {
            "emscripten/pybuilddir.txt": expected_hash,
        }
    }
    checksum_path = crate_dir / "vendor" / "pyo3" / ".cargo-checksum.json"
    checksum_path.parent.mkdir(parents=True, exist_ok=True)
    checksum_path.write_text(json.dumps(checksum), encoding="utf-8")


def test_vendor_recovery_materializes_missing_pybuilddir(tmp_path: Path) -> None:
    crate_dir = tmp_path / "crate"
    _write_checksum(crate_dir, _KNOWN_HASH)

    require_vendor(crate_dir)

    target = crate_dir / "vendor" / "pyo3" / "emscripten" / "pybuilddir.txt"
    assert target.exists()
    assert target.read_bytes() == _KNOWN_BYTES


def test_vendor_recovery_fails_for_unknown_expected_hash(tmp_path: Path) -> None:
    crate_dir = tmp_path / "crate"
    _write_checksum(crate_dir, "0" * 64)

    with pytest.raises(SASSystemBuildError) as exc:
        require_vendor(crate_dir)
    assert "INVALID:RUST_VENDOR_RECOVERY_UNAVAILABLE" in str(exc.value)


def test_vendor_recovery_rejects_checksum_mismatch_on_existing_file(tmp_path: Path) -> None:
    crate_dir = tmp_path / "crate"
    _write_checksum(crate_dir, _KNOWN_HASH)
    target = crate_dir / "vendor" / "pyo3" / "emscripten" / "pybuilddir.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"wrong")

    with pytest.raises(SASSystemBuildError) as exc:
        require_vendor(crate_dir)
    assert "INVALID:RUST_VENDOR_CHECKSUM_MISMATCH" in str(exc.value)
