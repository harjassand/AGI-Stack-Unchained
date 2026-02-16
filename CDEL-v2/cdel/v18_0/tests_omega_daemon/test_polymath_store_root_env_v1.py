from __future__ import annotations

import json
import shutil
from pathlib import Path

from cdel.v1_7r.canon import write_canon_json
from cdel.v18_0 import campaign_polymath_bootstrap_domain_v1 as bootstrap_campaign
from cdel.v18_0 import campaign_polymath_conquer_domain_v1 as conquer_campaign
from cdel.v18_0 import verify_rsi_polymath_domain_v1 as polymath_verifier
from cdel.v18_0.omega_common_v1 import Q32_ONE, load_canon_dict


def _write_void_row(path: Path) -> None:
    row = {
        "schema_version": "polymath_void_report_v1",
        "row_id": "sha256:" + ("1" * 64),
        "scanned_at_utc": "2026-02-09T00:00:00+00:00",
        "topic_id": "topic:env_store_demo",
        "topic_name": "Env Store Demo",
        "candidate_domain_id": "env_store_demo",
        "trend_score_q32": {"q": int(Q32_ONE)},
        "coverage_score_q32": {"q": 0},
        "void_score_q32": {"q": int(Q32_ONE)},
        "source_evidence": [
            {
                "url": "https://example.org/env_store_demo",
                "sha256": "sha256:" + ("2" * 64),
                "receipt_sha256": "sha256:" + ("3" * 64),
            }
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def test_polymath_campaigns_use_env_store_root(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    out_bootstrap = tmp_path / "out_bootstrap"
    out_conquer = tmp_path / "out_conquer"
    env_store_root = tmp_path / "env_store"

    write_canon_json(
        repo / "polymath" / "registry" / "polymath_domain_registry_v1.json",
        {"schema_version": "polymath_domain_registry_v1", "domains": []},
    )
    write_canon_json(
        repo / "polymath" / "domain_policy_v1.json",
        {
            "schema_version": "domain_policy_v1",
            "denylist_keywords": ["malware"],
            "allowlist_keywords": ["env", "store", "demo"],
        },
    )
    _write_void_row(repo / "polymath" / "registry" / "polymath_void_report_v1.jsonl")

    bootstrap_pack = tmp_path / "bootstrap_pack.json"
    write_canon_json(
        bootstrap_pack,
        {
            "schema_version": "rsi_polymath_bootstrap_domain_pack_v1",
            "domain_registry_path_rel": "polymath/registry/polymath_domain_registry_v1.json",
            "void_report_path_rel": "polymath/registry/polymath_void_report_v1.jsonl",
            "domain_policy_path_rel": "polymath/domain_policy_v1.json",
            "max_new_domains_u64": 1,
        },
    )

    monkeypatch.setattr(bootstrap_campaign, "repo_root", lambda: repo)
    monkeypatch.setattr(bootstrap_campaign, "emit_test_plan_receipt", lambda **_kwargs: ({}, {}))
    monkeypatch.setenv("OMEGA_POLYMATH_STORE_ROOT", env_store_root.as_posix())
    bootstrap_campaign.run(campaign_pack=bootstrap_pack, out_dir=out_bootstrap)

    bootstrap_report_path = out_bootstrap / "daemon" / "rsi_polymath_bootstrap_domain_v1" / "state" / "reports" / "polymath_bootstrap_report_v1.json"
    bootstrap_report = load_canon_dict(bootstrap_report_path)
    assert str(bootstrap_report.get("status", "")) == "BOOTSTRAPPED"
    assert (
        polymath_verifier.verify(
            out_bootstrap / "daemon" / "rsi_polymath_bootstrap_domain_v1" / "state",
            mode="full",
        )
        == "VALID"
    )

    domain_pack_rel = str(bootstrap_report.get("domain_pack_rel", ""))
    assert domain_pack_rel
    domain_pack_path = out_bootstrap / domain_pack_rel
    domain_pack = load_canon_dict(domain_pack_path)
    task = domain_pack["tasks"][0]
    split = task["split"]
    train_sha = str(split["train_sha256"])
    test_sha = str(split["test_sha256"])
    assert (env_store_root / "blobs" / "sha256" / train_sha.split(":", 1)[1]).exists()
    assert (env_store_root / "blobs" / "sha256" / test_sha.split(":", 1)[1]).exists()

    src_domain_dir = out_bootstrap / Path(domain_pack_rel).parent
    dst_domain_dir = repo / Path(domain_pack_rel).parent
    if dst_domain_dir.exists():
        shutil.rmtree(dst_domain_dir)
    dst_domain_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_domain_dir, dst_domain_dir)
    shutil.copyfile(
        out_bootstrap / "polymath" / "registry" / "polymath_domain_registry_v1.json",
        repo / "polymath" / "registry" / "polymath_domain_registry_v1.json",
    )

    shutil.rmtree(repo / "polymath" / "store", ignore_errors=True)

    conquer_pack = tmp_path / "conquer_pack.json"
    write_canon_json(
        conquer_pack,
        {
            "schema_version": "rsi_polymath_conquer_domain_pack_v1",
            "domain_registry_path_rel": "polymath/registry/polymath_domain_registry_v1.json",
            "require_improvement_b": True,
            "target_domain_id": str(bootstrap_report.get("domain_id", "")),
        },
    )

    monkeypatch.setattr(conquer_campaign, "repo_root", lambda: repo)
    monkeypatch.setattr(conquer_campaign, "emit_test_plan_receipt", lambda **_kwargs: ({}, {}))
    conquer_campaign.run(campaign_pack=conquer_pack, out_dir=out_conquer)
    assert (
        polymath_verifier.verify(
            out_conquer / "daemon" / "rsi_polymath_conquer_domain_v1" / "state",
            mode="full",
        )
        == "VALID"
    )
