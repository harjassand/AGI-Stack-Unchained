from __future__ import annotations

from cdel.v18_0.omega_promoter_v1 import _extract_activation_key


def test_science_activation_key_is_discovery_theory_id() -> None:
    theory_id = "sha256:" + ("a" * 64)
    promo = {
        "schema_version": "sas_science_promotion_bundle_v1",
        "discovery_bundle": {
            "theory_id": theory_id,
            "heldout_metrics": {
                "rmse_pos1_q32": {"q": "123", "schema_version": "q32_v1", "shift": 32},
            },
        },
    }
    key = _extract_activation_key("rsi_sas_science_v13_0", promo)
    assert key == theory_id
