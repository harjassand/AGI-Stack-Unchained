from __future__ import annotations

import pytest

from cdel.v18_0.omega_common_v1 import write_hashed_json
from cdel.v18_0.verify_rsi_omega_daemon_v1 import OmegaV18Error, verify
from .utils import latest_file, load_json, run_tick_once, write_json


def test_promoted_requires_meta_core_pass(tmp_path) -> None:
    _, state_dir = run_tick_once(tmp_path, tick_u64=1)

    promo_path = latest_file(state_dir / "dispatch", "*/promotion/sha256_*.omega_promotion_receipt_v1.json")
    promo_payload = load_json(promo_path)
    promo_payload["result"] = {"status": "PROMOTED", "reason_code": None}

    _, _, promo_hash = write_hashed_json(
        promo_path.parent,
        "omega_promotion_receipt_v1.json",
        promo_payload,
        id_field="receipt_id",
    )

    for path in promo_path.parent.glob("sha256_*.meta_core_promo_verify_receipt_v1.json"):
        path.unlink()
    plain = promo_path.parent / "meta_core_promo_verify_receipt_v1.json"
    if plain.exists():
        plain.unlink()

    snapshot_path = latest_file(state_dir / "snapshot", "sha256_*.omega_tick_snapshot_v1.json")
    snapshot = load_json(snapshot_path)
    snapshot["promotion_receipt_hash"] = promo_hash
    write_json(snapshot_path, snapshot)

    with pytest.raises(OmegaV18Error, match="DOWNSTREAM_META_CORE_FAIL"):
        verify(state_dir, mode="full")
