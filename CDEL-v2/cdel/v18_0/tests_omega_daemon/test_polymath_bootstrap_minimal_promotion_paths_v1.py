from __future__ import annotations

import json
from pathlib import Path

from cdel.v1_7r.canon import write_canon_json
from cdel.v18_0 import campaign_polymath_bootstrap_domain_v1 as bootstrap_campaign
from cdel.v18_0.omega_common_v1 import Q32_ONE


def _write_void_row(path: Path) -> None:
    row = {
        "schema_version": "polymath_void_report_v1",
        "row_id": "sha256:" + ("1" * 64),
        "scanned_at_utc": "2026-02-09T00:00:00+00:00",
        "topic_id": "topic:bootstrap_demo",
        "topic_name": "Bootstrap Demo",
        "candidate_domain_id": "bootstrap_demo",
        "trend_score_q32": {"q": int(Q32_ONE)},
        "coverage_score_q32": {"q": 0},
        "void_score_q32": {"q": int(Q32_ONE)},
        "source_evidence": [
            {
                "url": "https://example.org/bootstrap_demo",
                "sha256": "sha256:" + ("2" * 64),
                "receipt_sha256": "sha256:" + ("3" * 64),
            }
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def test_polymath_bootstrap_minimal_promotion_paths(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    out_dir = tmp_path / "out"
    pack_path = tmp_path / "bootstrap_pack.json"

    write_canon_json(
        repo / "polymath" / "registry" / "polymath_domain_registry_v1.json",
        {"schema_version": "polymath_domain_registry_v1", "domains": []},
    )
    write_canon_json(
        repo / "polymath" / "domain_policy_v1.json",
        {
            "schema_version": "domain_policy_v1",
            "denylist_keywords": ["malware"],
            "allowlist_keywords": ["bootstrap", "demo"],
        },
    )
    _write_void_row(repo / "polymath" / "registry" / "polymath_void_report_v1.jsonl")
    write_canon_json(
        pack_path,
        {
            "schema_version": "rsi_polymath_bootstrap_domain_pack_v1",
            "domain_registry_path_rel": "polymath/registry/polymath_domain_registry_v1.json",
            "void_report_path_rel": "polymath/registry/polymath_void_report_v1.jsonl",
            "domain_policy_path_rel": "polymath/domain_policy_v1.json",
            "max_new_domains_u64": 1,
        },
    )

    monkeypatch.setenv("OMEGA_POLYMATH_STORE_ROOT", (tmp_path / "store").as_posix())
    monkeypatch.setattr(bootstrap_campaign, "repo_root", lambda: repo)
    monkeypatch.setattr(bootstrap_campaign, "emit_test_plan_receipt", lambda **_kwargs: ({}, {}))
    bootstrap_campaign.run(campaign_pack=pack_path, out_dir=out_dir)

    bundle_rows = sorted(
        (out_dir / "daemon" / "rsi_polymath_bootstrap_domain_v1" / "state" / "promotion").glob(
            "sha256_*.polymath_bootstrap_promotion_bundle_v1.json"
        )
    )
    assert bundle_rows
    bundle = json.loads(bundle_rows[0].read_text(encoding="utf-8"))
    touched = [str(row) for row in bundle.get("touched_paths", [])]
    assert all("candidate_outputs_v1.json" not in row for row in touched)
    assert all("equivalence_report_v1.json" not in row for row in touched)
