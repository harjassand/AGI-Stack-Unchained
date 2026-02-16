from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from cdel.v1_7r.canon import sha256_prefixed, write_canon_json
from cdel.v15_1.verify_rsi_sas_kernel_v15_1 import V15_1KernelError, _validate_orchestrator_source_bundle


def test_run_contains_orchestrator_sources_or_bundle(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)

    with pytest.raises(V15_1KernelError):
        _validate_orchestrator_source_bundle(state_dir)

    bundle_path = state_dir / "orchestrator_source_bundle_v1.tar"
    member_rel = "orchestrator/sample.py"
    content = b"print('ok')\n"

    with tarfile.open(bundle_path, "w") as tar:
        info = tarfile.TarInfo(name=member_rel)
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))

    manifest = {
        "schema_version": "orchestrator_source_bundle_v1",
        "bundle_rel": "orchestrator_source_bundle_v1.tar",
        "bundle_sha256": sha256_prefixed(bundle_path.read_bytes()),
        "files": [{"path_rel": member_rel, "sha256": sha256_prefixed(content)}],
    }
    write_canon_json(state_dir / "orchestrator_source_bundle_v1.json", manifest)

    got = _validate_orchestrator_source_bundle(state_dir)
    assert got["bundle_sha256"] == manifest["bundle_sha256"]
