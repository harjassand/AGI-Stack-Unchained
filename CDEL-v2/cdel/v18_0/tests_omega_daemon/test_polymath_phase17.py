from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import write_canon_json
from cdel.v18_0 import campaign_polymath_scout_v1 as scout_campaign
from cdel.v18_0 import verify_rsi_polymath_scout_v1 as scout_verifier
from cdel.v18_0.omega_allowlists_v1 import load_allowlists
from cdel.v18_0.omega_common_v1 import canon_hash_obj, validate_schema
from cdel.v18_0.omega_promoter_v1 import run_promotion


def _sha(data: bytes) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(data).hexdigest()


def _write_fetch_receipt(path: Path, *, sha256: str, url: str) -> dict[str, Any]:
    payload = {
        "schema_version": "polymath_fetch_receipt_v1",
        "receipt_id": "sha256:" + ("0" * 64),
        "url": str(url),
        "request": {"headers": {}, "params": {}},
        "fetched_at_utc": "2026-02-09T00:00:00+00:00",
        "http_status": 200,
        "content_type": "application/json",
        "content_length_u64": 1,
        "etag": None,
        "last_modified": None,
        "sha256": str(sha256),
    }
    no_id = dict(payload)
    no_id.pop("receipt_id", None)
    payload["receipt_id"] = canon_hash_obj(no_id)
    write_canon_json(path, payload)
    return payload


def test_scout_campaign_writes_status_and_bundle(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    out_dir = tmp_path / "out"
    pack_path = tmp_path / "scout_pack.json"

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
            "max_blob_bytes_u64": 1024,
            "allowed_hosts": ["example.org"],
        },
    )

    def _fake_scout_void(**kwargs):  # noqa: ANN003
        out_void_path = Path(str(kwargs["void_report_path"]))
        out_store = Path(str(kwargs["store_root"]))
        blob_bytes = b'{"ok":1}'
        blob_sha = _sha(blob_bytes)
        blob_path = out_store / "blobs" / "sha256" / blob_sha.split(":", 1)[1]
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        blob_path.write_bytes(blob_bytes)

        receipt_path = out_store / "receipts" / "scout_receipt.json"
        receipt_payload = _write_fetch_receipt(receipt_path, sha256=blob_sha, url="https://example.org/topic")
        receipt_sha = canon_hash_obj(receipt_payload)
        row = {
            "schema_version": "polymath_void_report_v1",
            "row_id": "sha256:" + ("f" * 64),
            "scanned_at_utc": "2026-02-09T00:00:00+00:00",
            "topic_id": "topic:demo",
            "topic_name": "Demo",
            "candidate_domain_id": "demo",
            "trend_score_q32": {"q": 10},
            "coverage_score_q32": {"q": 0},
            "void_score_q32": {"q": 10},
            "source_evidence": [
                {
                    "url": "https://example.org/topic",
                    "sha256": blob_sha,
                    "receipt_sha256": receipt_sha,
                }
            ],
        }
        validate_schema(row, "polymath_void_report_v1")
        out_void_path.parent.mkdir(parents=True, exist_ok=True)
        out_void_path.write_text(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

        index_path = out_store / "indexes" / "urls_to_sha256.jsonl"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_row = {
            "schema_version": "polymath_url_index_v1",
            "request_hash": "sha256:" + ("1" * 64),
            "url": "https://example.org/topic",
            "sha256": blob_sha,
            "receipt_sha256": receipt_sha,
            "fetched_at_utc": "2026-02-09T00:00:00+00:00",
        }
        index_path.write_text(json.dumps(index_row, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        return {"rows_written_u64": 1, "top_rows": [row], "void_report_path": out_void_path.as_posix()}

    monkeypatch.setenv("OMEGA_TICK_U64", "123")
    monkeypatch.setattr(scout_campaign, "repo_root", lambda: repo)
    monkeypatch.setattr("tools.polymath.polymath_scout_v1.scout_void", _fake_scout_void)
    monkeypatch.setattr(scout_campaign, "emit_test_plan_receipt", lambda **_kwargs: ({}, {}))
    scout_campaign.run(campaign_pack=pack_path, out_dir=out_dir)

    status_payload = json.loads((out_dir / "polymath" / "registry" / "polymath_scout_status_v1.json").read_text(encoding="utf-8"))
    assert int(status_payload["tick_u64"]) == 123
    assert int(status_payload["rows_written_u64"]) == 1
    assert str(status_payload["schema_version"]) == "polymath_scout_status_v1"

    bundle_rows = sorted(
        (out_dir / "daemon" / "rsi_polymath_scout_v1" / "state" / "promotion").glob("sha256_*.polymath_scout_promotion_bundle_v1.json")
    )
    assert bundle_rows
    bundle = json.loads(bundle_rows[0].read_text(encoding="utf-8"))
    touched = set(bundle.get("touched_paths", []))
    assert "polymath/registry/polymath_void_report_v1.jsonl" in touched
    assert "polymath/registry/polymath_scout_status_v1.json" in touched


def test_scout_subverifier_validates_receipts_and_blobs(tmp_path: Path) -> None:
    subrun_root = tmp_path / "subrun"
    state_root = subrun_root / "daemon" / "rsi_polymath_scout_v1" / "state"
    (state_root / "reports").mkdir(parents=True, exist_ok=True)

    blob_bytes = b'{"ok":1}'
    blob_sha = _sha(blob_bytes)
    blob_path = subrun_root / "polymath" / "store" / "blobs" / "sha256" / blob_sha.split(":", 1)[1]
    blob_path.parent.mkdir(parents=True, exist_ok=True)
    blob_path.write_bytes(blob_bytes)

    receipt_path = subrun_root / "polymath" / "store" / "receipts" / "receipt.json"
    receipt_payload = _write_fetch_receipt(receipt_path, sha256=blob_sha, url="https://example.org/topic")
    receipt_sha = canon_hash_obj(receipt_payload)

    row = {
        "schema_version": "polymath_void_report_v1",
        "row_id": "sha256:" + ("f" * 64),
        "scanned_at_utc": "2026-02-09T00:00:00+00:00",
        "topic_id": "topic:demo",
        "topic_name": "Demo",
        "candidate_domain_id": "demo",
        "trend_score_q32": {"q": 100},
        "coverage_score_q32": {"q": 0},
        "void_score_q32": {"q": 100},
        "source_evidence": [
            {
                "url": "https://example.org/topic",
                "sha256": blob_sha,
                "receipt_sha256": receipt_sha,
            }
        ],
    }
    validate_schema(row, "polymath_void_report_v1")
    void_path = subrun_root / "polymath" / "registry" / "polymath_void_report_v1.jsonl"
    void_path.parent.mkdir(parents=True, exist_ok=True)
    void_path.write_text(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    status_payload = {
        "schema_version": "polymath_scout_status_v1",
        "scout_run_id": "sha256:" + ("0" * 64),
        "tick_u64": 7,
        "rows_written_u64": 1,
        "top_void_score_q32": {"q": 100},
        "topics_scanned_u64": 1,
        "sources_sha256s": [blob_sha],
    }
    no_id = dict(status_payload)
    no_id.pop("scout_run_id", None)
    status_payload["scout_run_id"] = canon_hash_obj(no_id)
    write_canon_json(subrun_root / "polymath" / "registry" / "polymath_scout_status_v1.json", status_payload)

    assert scout_verifier.verify(state_root, mode="full") == "VALID"


def test_promoter_rejects_missing_test_plan_receipt_for_required_campaign(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    dispatch_dir = state_root / "dispatch" / "a0"
    subrun_root = state_root / "subruns" / "a0_campaign"
    dispatch_dir.mkdir(parents=True)
    bundle_path = (
        subrun_root
        / "daemon"
        / "rsi_polymath_bootstrap_domain_v1"
        / "state"
        / "promotion"
        / "sha256_abcd.polymath_bootstrap_promotion_bundle_v1.json"
    )
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(
        bundle_path,
        {
            "schema_version": "polymath_bootstrap_promotion_bundle_v1",
            "campaign_id": "rsi_polymath_bootstrap_domain_v1",
            "domain_id": "demo",
            "activation_key": "demo",
            "touched_paths": ["polymath/registry/polymath_domain_registry_v1.json"],
        },
    )

    allowlists, _ = load_allowlists(
        Path(__file__).resolve().parents[4]
        / "campaigns"
        / "rsi_omega_daemon_v18_0"
        / "omega_allowlists_v1.json"
    )
    dispatch_ctx = {
        "dispatch_dir": dispatch_dir,
        "subrun_root_abs": subrun_root,
        "campaign_entry": {
            "campaign_id": "rsi_polymath_bootstrap_domain_v1",
            "capability_id": "RSI_POLYMATH_BOOTSTRAP_DOMAIN",
            "promotion_bundle_rel": "daemon/rsi_polymath_bootstrap_domain_v1/state/promotion/*.polymath_bootstrap_promotion_bundle_v1.json",
        },
    }
    receipt, _ = run_promotion(
        tick_u64=1,
        dispatch_ctx=dispatch_ctx,
        subverifier_receipt={"result": {"status": "VALID", "reason_code": None}},
        allowlists=allowlists,
    )
    assert receipt is not None
    assert receipt["result"]["status"] == "REJECTED"
    assert receipt["result"]["reason_code"] == "TEST_PLAN_RECEIPT_MISSING_OR_FAIL"
