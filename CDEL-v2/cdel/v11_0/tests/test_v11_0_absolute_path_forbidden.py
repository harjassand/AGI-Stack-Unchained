from __future__ import annotations

import pytest

from cdel.v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json
from cdel.v11_0.verify_rsi_arch_synthesis_v1 import verify
from .utils import build_valid_state


def test_absolute_path_forbidden(tmp_path):
    state = build_valid_state(tmp_path)
    receipt_dir = state["state_dir"] / "arch" / "build_receipts"
    receipt_path = next(receipt_dir.glob("sha256_*.sas_arch_build_receipt_v1.json"))
    receipt = load_canon_json(receipt_path)
    receipt["arch_ir_path"] = "/abs/path/forbidden.json"
    new_hash = sha256_prefixed(canon_bytes(receipt))
    new_path = receipt_dir / f"sha256_{new_hash.split(':',1)[1]}.sas_arch_build_receipt_v1.json"
    write_canon_json(new_path, receipt)
    receipt_path.unlink()
    with pytest.raises(Exception) as excinfo:
        verify(state["state_dir"], mode="prefix")
    assert "ABSOLUTE_PATH_FORBIDDEN" in str(excinfo.value)
