from __future__ import annotations

from cdel.v18_0.omega_common_v1 import canon_hash_obj, write_hashed_json
from .utils import load_json


def test_dispatch_receipt_recomputable(tmp_path) -> None:
    payload = {
        "schema_version": "omega_dispatch_receipt_v1",
        "receipt_id": "sha256:" + "0" * 64,
        "dispatch_attempted_b": True,
        "tick_u64": 7,
        "campaign_id": "rsi_sas_val_v17_0",
        "capability_id": "RSI_SAS_VAL",
        "invocation": {
            "py_module": "orchestrator.rsi_sas_val_v17_0",
            "argv": ["--campaign_pack", "campaigns/rsi_sas_val_v17_0/rsi_sas_val_pack_v17_0.json"],
            "env_fingerprint_hash": "sha256:" + "1" * 64,
        },
        "subrun": {
            "subrun_root_rel": "subruns/test",
            "state_dir_rel": "daemon/rsi_sas_val_v17_0/state",
            "subrun_tree_hash": "sha256:" + "2" * 64,
        },
        "stdout_hash": "sha256:" + "3" * 64,
        "stderr_hash": "sha256:" + "4" * 64,
        "return_code": 0,
    }
    path, written, digest = write_hashed_json(tmp_path, "omega_dispatch_receipt_v1.json", payload, id_field="receipt_id")

    loaded = load_json(path)
    assert digest == canon_hash_obj(loaded)

    no_id = dict(written)
    no_id.pop("receipt_id", None)
    assert written["receipt_id"] == canon_hash_obj(no_id)
