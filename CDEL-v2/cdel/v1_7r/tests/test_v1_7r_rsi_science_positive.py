from __future__ import annotations

from pathlib import Path

from cdel.v1_7r.canon import load_canon_json
from cdel.v1_7r.run_rsi_science_campaign import run_campaign
from cdel.v1_7r.verify_rsi_science import verify


def _repo_root() -> Path:
    # .../CDEL-v2/cdel/v1_7r/tests/test_*.py -> superproject root at parents[4]
    return Path(__file__).resolve().parents[4]


def test_v1_7r_rsi_science_positive(tmp_path: Path) -> None:
    repo_root = _repo_root()
    pack_path = repo_root / "campaigns" / "rsi_real_science_v1" / "rsi_science_campaign_pack_v1.json"
    campaign_pack = load_canon_json(pack_path)

    out_dir = tmp_path / "rsi_science_run"
    run_campaign(
        campaign_pack=campaign_pack,
        campaign_pack_path=pack_path,
        out_dir=out_dir,
        strict_rsi=True,
        strict_integrity=True,
        strict_science=True,
    )

    ok, reason = verify(out_dir)
    assert ok, reason
