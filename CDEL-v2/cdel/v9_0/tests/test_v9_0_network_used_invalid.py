from __future__ import annotations

from pathlib import Path

import hashlib
import pytest
from cdel.v1_7r.canon import CanonError, canon_bytes, load_canon_json, write_canon_json
from cdel.v9_0.verify_rsi_boundless_science_v1 import verify
from .utils import build_valid_state


def test_v9_0_network_used_invalid(tmp_path: Path) -> None:
    state = build_valid_state(tmp_path)
    sealed_dir = state["attempt_dir"] / "sealed"
    sealed_path = next(sealed_dir.glob("sha256_*.sealed_science_eval_receipt_v1.json"))
    sealed = load_canon_json(sealed_path)
    sealed_path.unlink()
    sealed["network_used"] = True
    new_hash = "sha256:" + hashlib.sha256(canon_bytes(sealed)).hexdigest()
    write_canon_json(sealed_dir / f"sha256_{new_hash.split(':',1)[1]}.sealed_science_eval_receipt_v1.json", sealed)
    with pytest.raises(CanonError, match="SCIENCE_NETWORK_USED"):
        verify(state["state_dir"], mode="prefix")
