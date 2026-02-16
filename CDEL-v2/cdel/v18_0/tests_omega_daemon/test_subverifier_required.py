from __future__ import annotations

import pytest

from cdel.v18_0.omega_common_v1 import write_hashed_json
from cdel.v18_0.verify_rsi_omega_daemon_v1 import OmegaV18Error, verify
from .utils import latest_file, load_json, run_tick_once, write_json


def test_subverifier_required(tmp_path) -> None:
    _, state_dir = run_tick_once(tmp_path, tick_u64=1)

    promo_payload = {
        "schema_version": "omega_promotion_receipt_v1",
        "receipt_id": "sha256:" + "0" * 64,
        "tick_u64": 1,
        "promotion_bundle_hash": "sha256:" + "5" * 64,
        "meta_core_verifier_fingerprint": {
            "constitution_meta_hash": "meta",
            "binary_hash_or_build_id": "kernel",
        },
        "result": {"status": "PROMOTED", "reason_code": None},
        "active_manifest_hash_after": "sha256:" + "6" * 64,
    }
    _, _, promo_hash = write_hashed_json(
        state_dir / "dispatch" / "fake" / "promotion",
        "omega_promotion_receipt_v1.json",
        promo_payload,
        id_field="receipt_id",
    )

    snapshot_path = latest_file(state_dir / "snapshot", "sha256_*.omega_tick_snapshot_v1.json")
    snapshot = load_json(snapshot_path)
    snapshot["promotion_receipt_hash"] = promo_hash
    snapshot["subverifier_receipt_hash"] = None
    write_json(snapshot_path, snapshot)

    with pytest.raises(OmegaV18Error, match="SUBVERIFIER_REQUIRED"):
        verify(state_dir, mode="full")
