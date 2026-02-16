from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v1_5r.canon import CanonError, load_canon_json, write_canon_json
from cdel.v1_5r.ctime.macro import compute_macro_id, compute_rent_bits
from cdel.v1_5r.run_rsi_campaign import run_campaign


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def test_v1_5r_rsi_integrity_requires_mined_rho(tmp_path: Path) -> None:
    base_pack_path = _repo_root() / "campaigns" / "rsi_real_integrity_v1" / "rsi_real_campaign_pack_v1.json"
    pack = load_canon_json(base_pack_path)
    pack["x-family_manifest"] = str(
        _repo_root() / "campaigns" / "rsi_real_integrity_v1" / "family_manifest_v1.json"
    )
    pack["enable_macro_miner"] = False
    pack["macro_proposal_epochs"] = [19]

    macro_def = {
        "schema": "macro_def_v1",
        "schema_version": 1,
        "macro_id": "",
        "body": [
            {"name": "RIGHT", "args": {"dir": 3}},
            {"name": "RIGHT", "args": {"dir": 3}},
            {"name": "RIGHT", "args": {"dir": 3}},
            {"name": "RIGHT", "args": {"dir": 3}},
        ],
        "guard": None,
        "admission_epoch": 0,
        "rent_bits": 0,
    }
    macro_def["rent_bits"] = compute_rent_bits(macro_def)
    macro_def["macro_id"] = compute_macro_id(macro_def)
    macro_path = tmp_path / "macro.json"
    write_canon_json(macro_path, macro_def)
    pack["macro_proposals_by_epoch"] = {"19": [str(macro_path)]}

    pack_path = tmp_path / "pack.json"
    write_canon_json(pack_path, pack)

    out_dir = tmp_path / "rsi_integrity_run"
    with pytest.raises(CanonError, match="macro provenance missing"):
        run_campaign(
            out_dir,
            {},
            strict_rsi=True,
            strict_integrity=True,
            enable_macro_miner=False,
            enable_policy_synthesizer=True,
            enable_family_generalizer=True,
            mode="real",
            campaign_pack=pack,
            pack_path=pack_path,
        )
