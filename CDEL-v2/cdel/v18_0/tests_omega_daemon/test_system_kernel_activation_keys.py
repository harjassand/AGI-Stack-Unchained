from __future__ import annotations

from cdel.v18_0.omega_promoter_v1 import _extract_activation_key
from cdel.v18_0.omega_common_v1 import canon_hash_obj


def test_system_activation_key_is_sealed_build_receipt_hash() -> None:
    value = "sha256:" + ("3" * 64)
    promo = {
        "schema_version": "sas_system_promotion_bundle_v1",
        "sealed_build_receipt_hash": value,
    }
    assert _extract_activation_key("rsi_sas_system_v14_0", promo) == value


def test_kernel_activation_key_prefers_kernel_binary_sha256() -> None:
    value = "sha256:" + ("4" * 64)
    promo = {
        "schema_version": "sas_kernel_promotion_bundle_v1",
        "kernel_binary_sha256": value,
        "kernel_activation_receipt": {"binary_sha256": "sha256:" + ("5" * 64)},
    }
    assert _extract_activation_key("rsi_sas_kernel_v15_0", promo) == value


def test_kernel_activation_key_falls_back_to_bundle_hash() -> None:
    promo = {
        "schema_version": "sas_kernel_promotion_bundle_v1",
        "campaign_id": "rsi_sas_kernel_v15_0",
    }
    assert _extract_activation_key("rsi_sas_kernel_v15_0", promo) == canon_hash_obj(promo)


def test_transpiler_activation_key_prefers_bundle_id() -> None:
    bundle_id = "sha256:" + ("6" * 64)
    promo = {
        "schema_version": "omega_promotion_bundle_native_transpiler_v1_1",
        "bundle_id": bundle_id,
        "native_binary_hash": "sha256:" + ("7" * 64),
    }
    assert _extract_activation_key("rsi_knowledge_transpiler_v1", promo) == bundle_id
