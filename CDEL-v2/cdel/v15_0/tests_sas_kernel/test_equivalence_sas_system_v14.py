from __future__ import annotations

from pathlib import Path

from cdel.v15_0.kernel_equivalence_v1 import build_equiv_report

from .utils import repo_root


def test_equivalence_sas_system_v14_fixture() -> None:
    root = repo_root()
    ref_snapshot = root / "campaigns" / "rsi_sas_kernel_v15_0" / "fixtures" / "rsi_sas_system_v14_0" / "immutable_tree_snapshot_v1.json"
    ref_promo = root / "campaigns" / "rsi_sas_kernel_v15_0" / "fixtures" / "rsi_sas_system_v14_0" / "kernel_promotion_bundle_v1.json"
    report = build_equiv_report(
        capability_id="RSI_SAS_SYSTEM_V14_0",
        snapshot_ref_path=ref_snapshot,
        snapshot_kernel_path=ref_snapshot,
        promotion_ref_path=ref_promo,
        promotion_kernel_path=ref_promo,
    )
    assert report["all_pass"] is True
