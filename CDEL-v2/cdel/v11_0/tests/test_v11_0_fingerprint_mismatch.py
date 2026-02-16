from __future__ import annotations

import pytest

from cdel.v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json
from cdel.v11_0.verify_rsi_arch_synthesis_v1 import verify
from .utils import build_valid_state


def test_fingerprint_mismatch(tmp_path):
    state = build_valid_state(tmp_path)
    fp_dir = state["state_dir"] / "arch" / "fingerprints"
    fp_path = next(fp_dir.glob("sha256_*.sas_topology_fingerprint_v1.json"))
    fp = load_canon_json(fp_path)
    fp["signature_hash"] = "sha256:" + "0" * 64
    new_hash = sha256_prefixed(canon_bytes(fp))
    new_path = fp_dir / f"sha256_{new_hash.split(':',1)[1]}.sas_topology_fingerprint_v1.json"
    write_canon_json(new_path, fp)
    fp_path.unlink()
    with pytest.raises(Exception) as excinfo:
        verify(state["state_dir"], mode="prefix")
    assert "FINGERPRINT_HASH_MISMATCH" in str(excinfo.value)
