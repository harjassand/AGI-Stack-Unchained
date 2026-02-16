from __future__ import annotations

import pytest

from cdel.v1_7r.canon import CanonError, load_canon_json, write_canon_json
from cdel.v3_2.verify_rsi_swarm_v3 import verify

from .utils import create_offer, setup_base_run


def test_v3_2_bridge_offer_hash_mismatch_fatal(tmp_path, repo_root) -> None:
    ctx = setup_base_run(tmp_path, repo_root, with_result=True)
    run_root = ctx["run_root"]
    offer_info = create_offer(run_root, ctx["run_id"], icore_id=ctx["icore_id"], task_id=ctx["task_id"], result_id=ctx["result_id"], verify_ref=ctx["verify_ref"])

    offer_path = run_root / "bridge_exchange" / "offers" / f"sha256_{offer_info['offer_id'].split(':',1)[1]}.bridge_offer_v1.json"
    offer = load_canon_json(offer_path)
    offer["offer_id"] = "sha256:" + "f" * 64
    offer["offer_hash"] = offer["offer_id"]
    write_canon_json(offer_path, offer)

    with pytest.raises(CanonError) as exc:
        verify(run_root)
    assert "BRIDGE_OFFER_HASH_MISMATCH" in str(exc.value)
