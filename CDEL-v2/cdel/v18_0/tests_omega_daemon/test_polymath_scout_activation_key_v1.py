from __future__ import annotations

from cdel.v18_0.omega_promoter_v1 import _extract_activation_key


def test_polymath_scout_activation_key_prefers_bundle_field() -> None:
    promo = {
        "schema_version": "polymath_scout_promotion_bundle_v1",
        "activation_key": "sha256:" + ("a" * 64),
        "scout_run_id": "sha256:" + ("b" * 64),
    }
    assert _extract_activation_key("rsi_polymath_scout_v1", promo) == promo["activation_key"]


def test_polymath_scout_activation_key_falls_back_to_bundle_hash() -> None:
    promo = {
        "schema_version": "polymath_scout_promotion_bundle_v1",
        "scout_run_id": "sha256:" + ("b" * 64),
        "rows_written_u64": 1,
    }
    key = _extract_activation_key("rsi_polymath_scout_v1", promo)
    assert isinstance(key, str) and key.startswith("sha256:") and len(key) == 71
