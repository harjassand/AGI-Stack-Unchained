from __future__ import annotations

import pytest

from cdel.v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json
from cdel.v11_1.verify_rsi_sas_math_v1 import verify

from .utils import build_state


def test_conjecture_not_in_bundle(tmp_path):
    state = build_state(tmp_path)
    sel_path = next((state.state_dir / "conjectures" / "selection").glob("sha256_*.sas_conjecture_selection_receipt_v1.json"))
    selection = load_canon_json(sel_path)
    selection["selected_conjecture_id"] = "sha256:" + "0" * 64
    receipt_hash = sha256_prefixed(canon_bytes({k: v for k, v in selection.items() if k != "receipt_id"}))
    selection["receipt_id"] = receipt_hash
    write_canon_json(sel_path, selection)

    with pytest.raises(Exception) as excinfo:
        verify(state.state_dir, mode="full")
    assert "CONJECTURE_NOT_IN_BUNDLE" in str(excinfo.value)
