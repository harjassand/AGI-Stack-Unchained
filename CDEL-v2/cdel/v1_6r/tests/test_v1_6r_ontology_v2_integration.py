from __future__ import annotations

import base64
from pathlib import Path

from cdel.v1_6r.run_rsi_campaign import run_campaign
from cdel.v1_6r.verify_rsi_ontology_v2 import verify


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def test_ontology_v2_campaign_integration(tmp_path: Path) -> None:
    repo = _repo_root()
    pack_path = repo / "campaigns" / "rsi_real_onto_v2" / "rsi_real_campaign_pack_v2.json"
    campaign_pack = __import__("json").loads(pack_path.read_text(encoding="utf-8"))

    out_dir = tmp_path / "run_onto_v2"
    master_key_b64 = base64.b64encode(b"\x01" * 32).decode("utf-8")

    run_campaign(
        out_dir,
        {},
        strict_rsi=False,
        strict_integrity=False,
        strict_portfolio=False,
        strict_transfer=False,
        mode="real",
        campaign_pack=campaign_pack,
        pack_path=pack_path,
        master_key_b64=master_key_b64,
    )

    ok, reason = verify(out_dir)
    assert ok, reason
