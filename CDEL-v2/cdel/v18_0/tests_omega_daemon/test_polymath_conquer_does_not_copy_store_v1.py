from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import write_canon_json
from cdel.v18_0 import campaign_polymath_conquer_domain_v1 as conquer_campaign
from cdel.v18_0.omega_common_v1 import load_canon_dict
from tools.polymath.polymath_domain_bootstrap_v1 import bootstrap_domain


def _bootstrap_repo_domain(repo_root: Path, *, store_root: Path, domain_id: str = "genomics_lite") -> dict[str, Any]:
    domains_root = repo_root / "domains"
    bootstrap = bootstrap_domain(
        domain_id=domain_id,
        domain_name="Genomics Lite",
        topic_ids=["topic:genomics_lite"],
        domains_root=domains_root,
        store_root=store_root,
        starter_size=18,
    )
    registry = {
        "schema_version": "polymath_domain_registry_v1",
        "domains": [
            {
                "domain_id": str(bootstrap["domain_id"]),
                "domain_name": "Genomics Lite",
                "status": "ACTIVE",
                "created_at_utc": "2026-02-09T00:00:00+00:00",
                "topic_ids": ["topic:genomics_lite"],
                "domain_pack_rel": f"domains/{bootstrap['domain_id']}/domain_pack_v1.json",
                "capability_id": f"RSI_DOMAIN_{str(bootstrap['domain_id']).upper()}",
                "dataset_artifact_sha256s": [],
                "ready_for_conquer": True,
                "ready_for_conquer_reason": "BOOTSTRAPPED",
                "conquered_b": False,
            }
        ],
    }
    write_canon_json(repo_root / "polymath" / "registry" / "polymath_domain_registry_v1.json", registry)
    return bootstrap


def test_polymath_conquer_does_not_copy_store(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    out_dir = tmp_path / "out"
    store_root = tmp_path / "store"
    pack_path = tmp_path / "conquer_pack.json"

    _bootstrap_repo_domain(repo, store_root=store_root)
    write_canon_json(
        pack_path,
        {
            "schema_version": "rsi_polymath_conquer_domain_pack_v1",
            "domain_registry_path_rel": "polymath/registry/polymath_domain_registry_v1.json",
            "require_improvement_b": False,
            "target_domain_id": "",
        },
    )

    monkeypatch.setenv("OMEGA_POLYMATH_STORE_ROOT", store_root.as_posix())
    monkeypatch.setattr(conquer_campaign, "repo_root", lambda: repo)
    monkeypatch.setattr(conquer_campaign, "emit_test_plan_receipt", lambda **_kwargs: ({}, {}))
    conquer_campaign.run(campaign_pack=pack_path, out_dir=out_dir)

    assert not (out_dir / "polymath" / "store").exists()
    bundle_rows = sorted(
        (out_dir / "daemon" / "rsi_polymath_conquer_domain_v1" / "state" / "promotion").glob(
            "sha256_*.polymath_conquer_promotion_bundle_v1.json"
        )
    )
    assert bundle_rows
    bundle = json.loads(bundle_rows[0].read_text(encoding="utf-8"))
    touched = [str(row) for row in bundle.get("touched_paths", [])]
    assert all("baseline_outputs_v1.json" not in row for row in touched)
    assert all("improved_outputs_v1.json" not in row for row in touched)

    report = load_canon_dict(
        out_dir / "daemon" / "rsi_polymath_conquer_domain_v1" / "state" / "reports" / "polymath_conquer_report_v1.json"
    )
    assert "baseline_outputs_rel" in report
    assert "improved_outputs_rel" in report
