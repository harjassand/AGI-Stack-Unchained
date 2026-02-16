from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json
from cdel.v15_1.verify_rsi_sas_kernel_v15_1 import V15_1KernelError, _validate_toolchain_manifest

from .utils import repo_root


def _toolchain_id(payload: dict[str, object]) -> str:
    raw = dict(payload)
    raw.pop("toolchain_id", None)
    return sha256_prefixed(canon_bytes(raw))


def test_toolchain_reject_true(tmp_path: Path) -> None:
    root = repo_root()
    schema_dir = root / "Genesis" / "schema" / "v15_1"

    src_manifest = root / "campaigns" / "rsi_sas_kernel_v15_1" / "toolchain_manifest_lean_v1.json"
    manifest = load_canon_json(src_manifest)
    manifest["checker_executable"] = "/usr/bin/true"
    manifest["invocation_template"] = ["/usr/bin/true"]
    manifest["checker_executable_hash"] = sha256_prefixed(Path("/usr/bin/true").resolve().read_bytes())
    manifest["toolchain_id"] = _toolchain_id(manifest)

    dst_manifest = tmp_path / "toolchain_manifest_lean_v1.json"
    write_canon_json(dst_manifest, manifest)

    with pytest.raises(V15_1KernelError):
        _validate_toolchain_manifest(dst_manifest, schema_dir)
