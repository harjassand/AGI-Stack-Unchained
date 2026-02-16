from __future__ import annotations

import pytest

from cdel.v1_7r.canon import CanonError
from cdel.v3_2.verify_rsi_swarm_v3 import verify

from .utils import create_offer, setup_base_run


def test_v3_2_bridge_blob_hash_mismatch_fatal(tmp_path, repo_root) -> None:
    ctx = setup_base_run(tmp_path, repo_root, with_result=True)
    run_root = ctx["run_root"]
    offer_info = create_offer(run_root, ctx["run_id"], icore_id=ctx["icore_id"], task_id=ctx["task_id"], result_id=ctx["result_id"], verify_ref=ctx["verify_ref"])
    # Tamper blob bytes after offer creation
    blob_path = offer_info["blob_path"]
    blob_path.write_bytes(b"tampered")

    with pytest.raises(CanonError) as exc:
        verify(run_root)
    assert "BRIDGE_BLOB_HASH_MISMATCH" in str(exc.value)
