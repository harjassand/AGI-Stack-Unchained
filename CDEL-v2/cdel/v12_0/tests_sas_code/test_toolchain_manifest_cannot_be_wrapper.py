from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v1_7r.canon import load_canon_json, write_canon_json
from cdel.v8_0.math_toolchain import compute_manifest_hash, compute_toolchain_id
from cdel.v12_0.verify_rsi_sas_code_v1 import verify

from .utils import build_state


def test_toolchain_manifest_cannot_be_wrapper(tmp_path: Path) -> None:
    state = build_state(tmp_path)
    manifest_path = state.config_dir / "sas_code_toolchain_manifest_lean4_v1.json"
    manifest = load_canon_json(manifest_path)
    manifest["invocation_template"] = ["/bin/true", "{entrypoint}"]
    manifest["toolchain_id"] = compute_toolchain_id(manifest)
    write_canon_json(manifest_path, manifest)

    new_hash = compute_manifest_hash(manifest)
    pack_path = state.config_dir / "rsi_sas_code_pack_v1.json"
    pack = load_canon_json(pack_path)
    pack["toolchain_manifest_hash"] = new_hash
    write_canon_json(pack_path, pack)

    with pytest.raises(Exception) as exc:
        verify(state.state_dir, mode="full")
    assert "INVALID:TOOLCHAIN_MANIFEST_INVALID" in str(exc.value)
