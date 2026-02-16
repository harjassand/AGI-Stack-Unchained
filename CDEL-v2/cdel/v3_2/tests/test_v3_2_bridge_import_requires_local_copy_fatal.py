from __future__ import annotations

import pytest

from cdel.v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed, write_canon_json
from cdel.v3_2.verify_rsi_swarm_v3 import verify

from .utils import create_import, create_offer, insert_before_swarm_end, setup_base_run, write_swarm_ledger


def test_v3_2_bridge_import_requires_local_copy_fatal(tmp_path, repo_root) -> None:
    ctx = setup_base_run(tmp_path, repo_root, with_result=True)
    run_root = ctx["run_root"]
    offer_info = create_offer(run_root, ctx["run_id"], icore_id=ctx["icore_id"], task_id=ctx["task_id"], result_id=ctx["result_id"], verify_ref=ctx["verify_ref"])
    import_info = create_import(run_root, offer_info["offer"])

    # Tamper manifest to use @ROOT path (non-local)
    manifest_path = run_root / import_info["manifest_rel"]
    manifest = load_canon_json(manifest_path)
    manifest["imports"][0]["local_blob_relpath"] = offer_info["offer"]["artifacts"][0]["exchange_blob_path"]
    imported_set_hash = sha256_prefixed(canon_bytes({"imports": manifest["imports"]}))
    manifest["imported_artifacts_set_hash"] = imported_set_hash
    write_canon_json(manifest_path, manifest)

    accept_payload = {
        "epoch_index": 1,
        "offer_id": import_info["offer_id"],
        "offer_path": f"@ROOT/bridge_exchange/offers/sha256_{import_info['offer_hex']}.bridge_offer_v1.json",
        "import_dir_relpath": import_info["import_dir_rel"],
        "import_manifest_relpath": import_info["manifest_rel"],
        "import_receipt_relpath": import_info["receipt_rel"],
        "imported_artifacts_set_hash": imported_set_hash,
    }
    insert_before_swarm_end(ctx["events"], "BRIDGE_IMPORT_ACCEPT", accept_payload)
    write_swarm_ledger(run_root / "ledger" / "swarm_ledger_v4.jsonl", ctx["events"])

    with pytest.raises(CanonError) as exc:
        verify(run_root)
    assert "BRIDGE_NONLOCAL_EVIDENCE" in str(exc.value)
