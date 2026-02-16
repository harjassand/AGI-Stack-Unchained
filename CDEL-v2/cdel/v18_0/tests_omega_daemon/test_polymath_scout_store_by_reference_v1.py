from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import write_canon_json
from cdel.v18_0 import campaign_polymath_scout_v1 as scout_campaign
from cdel.v18_0 import verify_rsi_polymath_scout_v1 as scout_verifier
from cdel.v18_0.omega_common_v1 import canon_hash_obj, validate_schema


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


def test_polymath_scout_store_by_reference(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    out_dir = tmp_path / "out"
    store_root = tmp_path / "store"
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
            "allowed_hosts": ["example.org"],
        },
    )

    def _fake_scout_void(**kwargs):  # noqa: ANN003
        out_void_path = Path(str(kwargs["void_report_path"]))
        resolved_store_root = Path(str(kwargs["store_root"]))
        blob_bytes = b'{"ok":1}'
        blob_sha = _sha(blob_bytes)
        blob_path = resolved_store_root / "blobs" / "sha256" / blob_sha.split(":", 1)[1]
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        blob_path.write_bytes(blob_bytes)

        receipt_path = resolved_store_root / "receipts" / "receipt.json"
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
        return {"rows_written_u64": 1}

    monkeypatch.setenv("OMEGA_TICK_U64", "7")
    monkeypatch.setenv("OMEGA_POLYMATH_STORE_ROOT", store_root.as_posix())
    monkeypatch.setattr(scout_campaign, "repo_root", lambda: repo)
    monkeypatch.setattr("tools.polymath.polymath_scout_v1.scout_void", _fake_scout_void)
    monkeypatch.setattr(scout_campaign, "emit_test_plan_receipt", lambda **_kwargs: ({}, {}))
    scout_campaign.run(campaign_pack=pack_path, out_dir=out_dir)

    assert not (out_dir / "polymath" / "store").exists()
    state_root = out_dir / "daemon" / "rsi_polymath_scout_v1" / "state"
    assert scout_verifier.verify(state_root, mode="full") == "VALID"

    bundle_rows = sorted((state_root / "promotion").glob("sha256_*.polymath_scout_promotion_bundle_v1.json"))
    assert bundle_rows
    bundle = json.loads(bundle_rows[0].read_text(encoding="utf-8"))
    touched = sorted(str(row) for row in bundle.get("touched_paths", []))
    assert touched == [
        "polymath/registry/polymath_scout_status_v1.json",
        "polymath/registry/polymath_void_report_v1.jsonl",
    ]
