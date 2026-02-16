from __future__ import annotations

from pathlib import Path

from cdel.v1_7r.canon import load_canon_json
from cdel.v18_0.campaign_ge_symbiotic_optimizer_sh1_v0_1 import run


def test_campaign_ge_sh1_emits_ccap_bundle_v1(tmp_path, monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[4]
    campaign_pack = repo_root / "campaigns" / "rsi_ge_symbiotic_optimizer_sh1_v0_1" / "rsi_ge_symbiotic_optimizer_sh1_pack_v0_1.json"
    out_dir = tmp_path / "campaign_out"

    monkeypatch.setenv("OMEGA_GE_STATE_ROOT", str(tmp_path / "ge_state"))
    monkeypatch.setenv("OMEGA_RUN_SEED_U64", "11")

    run(campaign_pack=campaign_pack, out_dir=out_dir)

    promotion_dir = out_dir / "promotion"
    bundles = sorted(promotion_dir.glob("sha256_*.omega_promotion_bundle_ccap_v1.json"), key=lambda row: row.as_posix())
    assert len(bundles) == 1

    bundle = load_canon_json(bundles[0])
    assert bundle["touched_paths"] == [bundle["ccap_relpath"], bundle["patch_relpath"]]
