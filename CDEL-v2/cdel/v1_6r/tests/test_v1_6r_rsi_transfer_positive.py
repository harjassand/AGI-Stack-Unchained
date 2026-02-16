from __future__ import annotations

from pathlib import Path

from cdel.v1_6r.canon import load_canon_json
from cdel.v1_6r.run_rsi_campaign import run_campaign
from cdel.v1_6r.verify_rsi_transfer import verify as verify_transfer


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def test_v1_6r_rsi_transfer_positive(tmp_path: Path) -> None:
    pack_path = _repo_root() / "campaigns" / "rsi_real_transfer_v1" / "rsi_real_campaign_pack_v2.json"
    campaign_pack = load_canon_json(pack_path)
    out_dir = tmp_path / "rsi_transfer_run"
    run_campaign(
        out_dir,
        {},
        strict_rsi=True,
        strict_integrity=True,
        strict_portfolio=True,
        strict_transfer=True,
        enable_macro_miner=True,
        enable_policy_synthesizer=True,
        enable_family_generalizer=False,
        enable_witness_emission=True,
        enable_witness_family_generalizer_v2=True,
        enable_mech_patch_searcher=True,
        mode="real",
        campaign_pack=campaign_pack,
        pack_path=pack_path,
    )

    ok, reason = verify_transfer(out_dir)
    assert ok, reason
