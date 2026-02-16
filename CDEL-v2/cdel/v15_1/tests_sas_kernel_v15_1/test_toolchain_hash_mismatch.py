from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v1_7r.canon import canon_bytes, sha256_prefixed, write_canon_json
from cdel.v15_1.verify_rsi_sas_kernel_v15_1 import V15_1KernelError, _validate_toolchain_manifest

from .utils import repo_root


def _toolchain_id(payload: dict[str, object]) -> str:
    raw = dict(payload)
    raw.pop("toolchain_id", None)
    return sha256_prefixed(canon_bytes(raw))


def test_toolchain_hash_mismatch(tmp_path: Path) -> None:
    root = repo_root()
    schema_dir = root / "Genesis" / "schema" / "v15_1"

    fake_lean = tmp_path / "lean"
    fake_lean.write_text("#!/bin/sh\necho fake lean\n", encoding="utf-8")
    fake_lean.chmod(0o755)

    manifest: dict[str, object] = {
        "checker_name": "lean_runner",
        "checker_executable": str(fake_lean.resolve()),
        "invocation_template": [str(fake_lean.resolve())],
        "checker_executable_hash": "sha256:" + ("1" * 64),
    }
    manifest["toolchain_id"] = _toolchain_id(manifest)

    manifest_path = tmp_path / "toolchain_manifest_lean_v1.json"
    write_canon_json(manifest_path, manifest)

    with pytest.raises(V15_1KernelError):
        _validate_toolchain_manifest(manifest_path, schema_dir)
