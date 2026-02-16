from __future__ import annotations

from pathlib import Path

from cdel.v1_5r.canon import load_canon_json
from cdel.v1_5r.run_rsi_campaign import run_campaign
from cdel.v1_5r.verify_rsi_portfolio import verify as verify_portfolio


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def test_v1_5r_rsi_portfolio_positive(tmp_path: Path) -> None:
    pack_path = _repo_root() / "campaigns" / "rsi_real_portfolio_v1" / "rsi_real_campaign_pack_v1.json"
    campaign_pack = load_canon_json(pack_path)
    out_dir = tmp_path / "rsi_portfolio_run"
    run_campaign(
        out_dir,
        {},
        strict_rsi=True,
        strict_integrity=True,
        strict_portfolio=True,
        enable_macro_miner=True,
        enable_policy_synthesizer=True,
        enable_family_generalizer=True,
        enable_meta_patch_searcher=True,
        mode="real",
        campaign_pack=campaign_pack,
        pack_path=pack_path,
    )

    ok, reason = verify_portfolio(out_dir)
    assert ok, reason

    receipts = list(out_dir.glob("epochs/epoch_*/diagnostics/rsi_portfolio_receipt_v1.json"))
    assert len(receipts) == 1
