from __future__ import annotations

from cdel.v18_0.omega_promoter_v1 import _extract_activation_key


def test_model_genesis_activation_key_prefers_bundle_id() -> None:
    promo = {
        "schema_version": "model_promotion_bundle_v1",
        "bundle_id": "sha256:" + ("a" * 64),
        "icore_id": "sha256:" + ("b" * 64),
    }
    assert _extract_activation_key("rsi_model_genesis_v10_0", promo) == promo["bundle_id"]


def test_model_genesis_activation_key_falls_back_to_icore_id() -> None:
    promo = {
        "schema_version": "model_promotion_bundle_v1",
        "icore_id": "sha256:" + ("b" * 64),
    }
    assert _extract_activation_key("rsi_model_genesis_v10_0", promo) == promo["icore_id"]


def test_model_genesis_activation_key_falls_back_to_bundle_hash() -> None:
    promo = {
        "schema_version": "model_promotion_bundle_v1",
        "meta_hash": "x",
    }
    key = _extract_activation_key("rsi_model_genesis_v10_0", promo)
    assert isinstance(key, str) and key.startswith("sha256:") and len(key) == 71

