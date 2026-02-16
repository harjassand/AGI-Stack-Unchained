from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from cdel.v1_7r.canon import write_canon_json
from cdel.v18_0 import campaign_polymath_conquer_domain_v1 as conquer_campaign
from cdel.v18_0.omega_common_v1 import load_canon_dict


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _seed_script() -> Path:
    return _repo_root() / "tools" / "polymath" / "polymath_seed_flagships_v1.py"


def _proposer_script() -> Path:
    return _repo_root() / "tools" / "polymath" / "polymath_refinery_proposer_v1.py"


def test_refinery_end_to_end_pubchem_conquer_not_no_ready(monkeypatch, tmp_path: Path) -> None:
    store_root = tmp_path / "store"
    out_dir = tmp_path / "out"
    proposer_summary = tmp_path / "proposer.json"
    seed_summary = tmp_path / "seed.json"
    pack_path = tmp_path / "conquer_pack.json"

    seed_run = subprocess.run(
        [
            sys.executable,
            str(_seed_script()),
            "--store_root",
            str(store_root),
            "--summary_path",
            str(seed_summary),
        ],
        cwd=_repo_root(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert int(seed_run.returncode) == 0, seed_run.stderr

    proposer_run = subprocess.run(
        [
            sys.executable,
            str(_proposer_script()),
            "--registry_path",
            str(_repo_root() / "polymath" / "registry" / "polymath_domain_registry_v1.json"),
            "--store_root",
            str(store_root),
            "--workers",
            "2",
            "--max_domains",
            "32",
            "--summary_path",
            str(proposer_summary),
        ],
        cwd=_repo_root(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert int(proposer_run.returncode) == 0, proposer_run.stderr

    write_canon_json(
        pack_path,
        {
            "schema_version": "rsi_polymath_conquer_domain_pack_v1",
            "domain_registry_path_rel": "polymath/registry/polymath_domain_registry_v1.json",
            "require_improvement_b": False,
            "target_domain_id": "pubchem_weight300",
        },
    )

    monkeypatch.setenv("OMEGA_POLYMATH_STORE_ROOT", store_root.as_posix())
    monkeypatch.setattr(conquer_campaign, "repo_root", lambda: _repo_root())
    monkeypatch.setattr(conquer_campaign, "emit_test_plan_receipt", lambda **_kwargs: ({}, {}))
    conquer_campaign.run(campaign_pack=pack_path, out_dir=out_dir)

    report = load_canon_dict(
        out_dir / "daemon" / "rsi_polymath_conquer_domain_v1" / "state" / "reports" / "polymath_conquer_report_v1.json"
    )
    assert str(report.get("status", "")) in {"IMPROVED", "NO_IMPROVEMENT"}
    assert str(report.get("status", "")) != "NO_READY_DOMAIN"
    assert bool(report.get("refinery_cache_hit_b", False)) is True
