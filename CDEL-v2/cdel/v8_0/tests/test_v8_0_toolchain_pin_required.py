from __future__ import annotations

from pathlib import Path

import pytest
from cdel.v1_7r.canon import CanonError, load_canon_json, write_canon_json
from cdel.v8_0.math_toolchain import compute_toolchain_id
from cdel.v8_0.verify_rsi_boundless_math_v1 import verify
from .utils import build_valid_state


def test_v8_0_toolchain_pin_required(tmp_path: Path) -> None:
    state = build_valid_state(tmp_path)
    manifest_path = state["daemon_root"] / "config" / "math_toolchain_manifest_v1.json"
    manifest = load_canon_json(manifest_path)
    manifest["checker_version"] = "4.0.0-tamper"
    manifest["toolchain_id"] = compute_toolchain_id(manifest)
    write_canon_json(manifest_path, manifest)
    with pytest.raises(CanonError, match="BOUNDLESS_MATH_TOOLCHAIN_DRIFT"):
        verify(state["state_dir"], mode="prefix")
