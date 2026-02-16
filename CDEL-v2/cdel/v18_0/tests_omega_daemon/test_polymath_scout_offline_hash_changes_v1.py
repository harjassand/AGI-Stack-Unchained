from __future__ import annotations

from pathlib import Path

from cdel.v1_7r.canon import write_canon_json
from cdel.v18_0 import campaign_polymath_scout_v1 as scout_campaign
from cdel.v18_0 import verify_rsi_polymath_scout_v1 as scout_verifier
from cdel.v18_0.omega_common_v1 import hash_file_stream, load_jsonl


def _write_fixture(repo: Path, pack_path: Path) -> None:
    write_canon_json(
        repo / "polymath" / "registry" / "polymath_domain_registry_v1.json",
        {"schema_version": "polymath_domain_registry_v1", "domains": []},
    )
    write_canon_json(
        repo / "polymath" / "domain_policy_v1.json",
        {"schema_version": "domain_policy_v1", "allowlist_keywords": ["science"], "denylist_keywords": ["malware"]},
    )
    write_canon_json(
        pack_path,
        {
            "schema_version": "rsi_polymath_scout_pack_v1",
            "domain_registry_path_rel": "polymath/registry/polymath_domain_registry_v1.json",
            "void_report_path_rel": "polymath/registry/polymath_void_report_v1.jsonl",
            "domain_policy_path_rel": "polymath/domain_policy_v1.json",
            "scout_status_path_rel": "polymath/registry/polymath_scout_status_v1.json",
            "max_topics_u64": 1,
            "delay_seconds_f64": 0,
            "allowed_hosts": ["example.org"],
        },
    )


def test_scout_offline_fallback_changes_void_hash_by_tick(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    store_root = tmp_path / "store"
    pack_path = tmp_path / "scout_pack.json"
    _write_fixture(repo, pack_path)

    def _raise_offline(**_kwargs):  # noqa: ANN003
        raise RuntimeError("offline")

    monkeypatch.setattr(scout_campaign, "repo_root", lambda: repo)
    monkeypatch.setattr("tools.polymath.polymath_scout_v1.scout_void", _raise_offline)
    monkeypatch.setattr(scout_campaign, "emit_test_plan_receipt", lambda **_kwargs: ({}, {}))
    monkeypatch.setenv("OMEGA_POLYMATH_STORE_ROOT", store_root.as_posix())

    void_hashes: list[str] = []
    row_ids: list[str] = []
    for tick_u64, run_name in ((11, "run_a"), (12, "run_b")):
        out_dir = tmp_path / run_name
        monkeypatch.setenv("OMEGA_TICK_U64", str(tick_u64))
        scout_campaign.run(campaign_pack=pack_path, out_dir=out_dir)

        void_path = out_dir / "polymath" / "registry" / "polymath_void_report_v1.jsonl"
        rows = load_jsonl(void_path)
        assert len(rows) == 1
        row = rows[0]
        assert str(row.get("schema_version", "")) == "polymath_void_report_v1"
        assert str(row.get("candidate_domain_id", "")) == f"offline::{int(tick_u64)}"
        assert str(row.get("topic_id", "")) == "offline"
        assert str(row.get("topic_name", "")) == "offline"
        assert int((row.get("void_score_q32") or {}).get("q", 0)) == 1
        evidence = row.get("source_evidence")
        assert isinstance(evidence, list) and len(evidence) == 1
        void_hashes.append(hash_file_stream(void_path))
        row_ids.append(str(row.get("row_id", "")))
        state_root = out_dir / "daemon" / "rsi_polymath_scout_v1" / "state"
        assert scout_verifier.verify(state_root, mode="full") == "VALID"

    assert void_hashes[0] != void_hashes[1]
    assert row_ids[0] != row_ids[1]
