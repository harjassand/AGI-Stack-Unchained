from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v1_7r.canon import write_canon_json
from cdel.v15_0.kernel_pinning_v1 import KernelPinningError, load_toolchain_manifest


def test_negative_toolchain_spoof(tmp_path: Path) -> None:
    manifest = {
        "checker_name": "pytest_spoof",
        "invocation_template": ["/usr/bin/true"],
        "checker_executable_hash": "sha256:" + ("2" * 64),
        "toolchain_id": "",
    }
    from cdel.v1_7r.canon import canon_bytes, sha256_prefixed

    payload = dict(manifest)
    payload.pop("toolchain_id")
    manifest["toolchain_id"] = sha256_prefixed(canon_bytes(payload))

    path = tmp_path / "toolchain.json"
    write_canon_json(path, manifest)
    with pytest.raises(KernelPinningError):
        load_toolchain_manifest(path)
