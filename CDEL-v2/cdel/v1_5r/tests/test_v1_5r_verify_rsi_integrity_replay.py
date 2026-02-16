from __future__ import annotations

from pathlib import Path

from cdel.v1_5r.canon import load_canon_json
from cdel.v1_5r.run_rsi_campaign import run_campaign
from cdel.v1_5r.verify_rsi_integrity import verify as verify_integrity


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def test_v1_5r_verify_rsi_integrity_replay(tmp_path: Path) -> None:
    pack_path = _repo_root() / "campaigns" / "rsi_real_integrity_v1" / "rsi_real_campaign_pack_v1.json"
    campaign_pack = load_canon_json(pack_path)
    out_dir = tmp_path / "rsi_integrity_run"
    run_campaign(
        out_dir,
        {},
        strict_rsi=True,
        strict_integrity=True,
        enable_macro_miner=True,
        enable_policy_synthesizer=True,
        enable_family_generalizer=True,
        mode="real",
        campaign_pack=campaign_pack,
        pack_path=pack_path,
    )

    ok, reason = verify_integrity(out_dir)
    assert ok, reason
