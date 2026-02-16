from __future__ import annotations

from pathlib import Path

from cdel.v16_1.verify_rsi_sas_metasearch_v16_1 import verify


def test_replay_independent_of_campaign_filenames(v16_1_run_root: Path) -> None:
    state = v16_1_run_root / "daemon" / "rsi_sas_metasearch_v16_1" / "state"
    campaign_datasets = Path("campaigns/rsi_sas_metasearch_v16_1/datasets")

    pairs = [
        (campaign_datasets / "gravity_dataset_manifest_v1.json", campaign_datasets / "gravity_dataset_manifest_v1.renamed"),
        (campaign_datasets / "gravity_dataset.csv", campaign_datasets / "gravity_dataset.renamed.csv"),
    ]

    for src, dst in pairs:
        src.rename(dst)
    try:
        assert verify(state, mode="full") == "VALID"
    finally:
        for src, dst in pairs:
            if dst.exists():
                dst.rename(src)
