from __future__ import annotations

import pytest

from cdel.v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json
from cdel.v11_0.verify_rsi_arch_synthesis_v1 import verify
from .utils import build_valid_state


def test_missing_training_ledger_head(tmp_path):
    state = build_valid_state(tmp_path)
    bundle_path = state["weights_bundle_path"]
    bundle = load_canon_json(bundle_path)
    bundle.pop("training_ledger_head_hash", None)
    new_hash = sha256_prefixed(canon_bytes(bundle))
    new_path = bundle_path.parent / f"sha256_{new_hash.split(':',1)[1]}.sas_weights_bundle_v1.json"
    write_canon_json(new_path, bundle)
    bundle_path.unlink()
    with pytest.raises(Exception) as excinfo:
        verify(state["state_dir"], mode="prefix")
    assert "WEIGHTS_BUNDLE_MISSING_TRAINING_LEDGER_HEAD" in str(excinfo.value)
