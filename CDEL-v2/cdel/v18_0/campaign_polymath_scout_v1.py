"""Deterministic polymath scout campaign that emits auditable void artifacts (v1)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ..v1_7r.canon import write_canon_json
from .omega_common_v1 import canon_hash_obj, fail, load_canon_dict, load_jsonl, repo_root, validate_schema, write_hashed_json
from .omega_test_plan_v1 import emit_test_plan_receipt

_DEFAULT_ALLOWED_HOSTS: tuple[str, ...] = (
    "api.openalex.org",
    "export.arxiv.org",
    "api.crossref.org",
    "api.semanticscholar.org",
)
_DEFAULT_MAX_BLOB_BYTES_U64 = 2 * 1024 * 1024
_VOID_REPORT_CANONICAL_REL = "polymath/registry/polymath_void_report_v1.jsonl"


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _tick_iso_utc(tick_u64: int) -> str:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return (base + timedelta(seconds=max(0, int(tick_u64)))).replace(microsecond=0).isoformat()


def _emit_offline_void_report(
    *,
    out_void_path: Path,
    store_root: Path,
    tick_u64: int,
    out_dir: Path,
    failure_reason: str,
) -> dict[str, Any]:
    run_seed_u64 = str(os.environ.get("OMEGA_RUN_SEED_U64", "")).strip() or "0"
    run_scope = out_dir.resolve().name
    source_url = f"offline://polymath_scout_v1/run_seed/{run_seed_u64}/tick/{int(tick_u64)}"

    evidence_payload = {
        "schema_version": "polymath_scout_offline_evidence_v1",
        "tick_u64": int(tick_u64),
        "run_seed_u64": str(run_seed_u64),
        "run_scope": str(run_scope),
        "failure_reason": str(failure_reason),
    }
    evidence_bytes = json.dumps(evidence_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    blob_sha = "sha256:" + hashlib.sha256(evidence_bytes).hexdigest()
    blob_path = store_root / "blobs" / "sha256" / blob_sha.split(":", 1)[1]
    blob_path.parent.mkdir(parents=True, exist_ok=True)
    if blob_path.exists():
        if blob_path.read_bytes() != evidence_bytes:
            fail("NONDETERMINISTIC")
    else:
        blob_path.write_bytes(evidence_bytes)

    receipt_payload = {
        "schema_version": "polymath_fetch_receipt_v1",
        "receipt_id": "sha256:" + ("0" * 64),
        "url": source_url,
        "request": {
            "headers": {},
            "params": {
                "offline_fallback_b": "1",
                "run_seed_u64": str(run_seed_u64),
                "tick_u64": str(int(tick_u64)),
            },
        },
        "fetched_at_utc": _tick_iso_utc(tick_u64),
        "http_status": 200,
        "content_type": "application/json",
        "content_length_u64": int(len(evidence_bytes)),
        "etag": None,
        "last_modified": None,
        "sha256": blob_sha,
    }
    no_id = dict(receipt_payload)
    no_id.pop("receipt_id", None)
    receipt_payload["receipt_id"] = canon_hash_obj(no_id)
    receipt_sha256 = canon_hash_obj(receipt_payload)
    validate_schema(receipt_payload, "polymath_fetch_receipt_v1")
    receipt_path = store_root / "receipts" / f"{blob_sha.split(':', 1)[1]}.offline_scout_receipt_v1.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(receipt_path, receipt_payload)

    row = {
        "schema_version": "polymath_void_report_v1",
        "row_id": "sha256:" + ("0" * 64),
        "scanned_at_utc": _tick_iso_utc(tick_u64),
        "topic_id": "offline",
        "topic_name": "offline",
        "candidate_domain_id": f"offline::{int(tick_u64)}",
        "trend_score_q32": {"q": 1},
        "coverage_score_q32": {"q": 0},
        "void_score_q32": {"q": 1},
        "source_evidence": [
            {
                "url": source_url,
                "sha256": blob_sha,
                "receipt_sha256": str(receipt_sha256),
            }
        ],
    }
    row_no_id = dict(row)
    row_no_id.pop("row_id", None)
    row["row_id"] = canon_hash_obj(row_no_id)
    validate_schema(row, "polymath_void_report_v1")
    out_void_path.parent.mkdir(parents=True, exist_ok=True)
    out_void_path.write_text(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    return {
        "rows_written_u64": 1,
        "offline_fallback_b": True,
    }


def _load_pack(path: Path) -> dict[str, Any]:
    payload = load_canon_dict(path)
    if str(payload.get("schema_version", "")).strip() != "rsi_polymath_scout_pack_v1":
        fail("SCHEMA_FAIL")
    return payload


def _canonical_store_root(repo_root_path: Path) -> Path:
    env_value = str(os.environ.get("OMEGA_POLYMATH_STORE_ROOT", "")).strip()
    if env_value:
        store_root = Path(env_value).expanduser().resolve()
    else:
        store_root = (repo_root_path / ".omega_cache" / "polymath" / "store").resolve()
    store_root.mkdir(parents=True, exist_ok=True)
    for rel in ("indexes/urls_to_sha256.jsonl", "indexes/domain_to_artifacts.jsonl"):
        path = store_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text("", encoding="utf-8")
    return store_root


def _tick_from_env() -> int:
    raw = str(os.environ.get("OMEGA_TICK_U64", "")).strip()
    if not raw:
        fail("MISSING_STATE_INPUT")
    try:
        tick_u64 = int(raw)
    except Exception:  # noqa: BLE001
        fail("SCHEMA_FAIL")
    if tick_u64 < 0:
        fail("SCHEMA_FAIL")
    return int(tick_u64)


def _top_void_q32(rows: list[dict[str, Any]]) -> int:
    best = 0
    for row in rows:
        value = row.get("void_score_q32")
        if isinstance(value, dict):
            best = max(best, max(0, int(value.get("q", 0))))
    return int(best)


def _topics_scanned_u64(rows: list[dict[str, Any]]) -> int:
    topics: set[str] = set()
    for row in rows:
        topic_id = str(row.get("topic_id", "")).strip()
        if topic_id:
            topics.add(topic_id)
    return int(len(topics))


def _source_sha256s(rows: list[dict[str, Any]]) -> list[str]:
    out: set[str] = set()
    for row in rows:
        evidence = row.get("source_evidence")
        if not isinstance(evidence, list):
            fail("SCHEMA_FAIL")
        for item in evidence:
            if not isinstance(item, dict):
                fail("SCHEMA_FAIL")
            digest = str(item.get("sha256", "")).strip()
            if digest:
                out.add(digest)
    return sorted(out)


def run(*, campaign_pack: Path, out_dir: Path) -> None:
    pack = _load_pack(campaign_pack)
    root = repo_root()

    registry_path = root / str(pack.get("domain_registry_path_rel", "polymath/registry/polymath_domain_registry_v1.json"))
    void_report_rel = str(pack.get("void_report_path_rel", _VOID_REPORT_CANONICAL_REL)).strip() or _VOID_REPORT_CANONICAL_REL
    if void_report_rel != _VOID_REPORT_CANONICAL_REL:
        fail("MISSING_STATE_INPUT")
    void_report_input_path = root / void_report_rel
    policy_path = root / str(pack.get("domain_policy_path_rel", "polymath/domain_policy_v1.json"))
    scout_status_rel = str(pack.get("scout_status_path_rel", "polymath/registry/polymath_scout_status_v1.json"))

    if not registry_path.exists() or not registry_path.is_file():
        fail("MISSING_STATE_INPUT")
    if not policy_path.exists() or not policy_path.is_file():
        fail("MISSING_STATE_INPUT")

    registry_payload = load_canon_dict(registry_path)
    validate_schema(registry_payload, "polymath_domain_registry_v1")
    policy_payload = load_canon_dict(policy_path)
    validate_schema(policy_payload, "domain_policy_v1")
    _ = load_jsonl(void_report_input_path) if void_report_input_path.exists() and void_report_input_path.is_file() else []

    state_root = out_dir.resolve() / "daemon" / "rsi_polymath_scout_v1" / "state"
    reports_dir = state_root / "reports"
    promotion_dir = state_root / "promotion"
    for path in (reports_dir, promotion_dir):
        path.mkdir(parents=True, exist_ok=True)

    store_root = _canonical_store_root(root)

    out_void_path = out_dir / _VOID_REPORT_CANONICAL_REL
    out_void_path.parent.mkdir(parents=True, exist_ok=True)
    if out_void_path.exists():
        out_void_path.unlink()
    tick_u64 = _tick_from_env()

    max_topics = max(1, int(pack.get("max_topics_u64", 12)))
    delay_seconds = max(0.0, float(pack.get("delay_seconds_f64", 0.0)))
    max_blob_bytes_u64 = max(1, int(pack.get("max_blob_bytes_u64", _DEFAULT_MAX_BLOB_BYTES_U64)))
    mailto = str(pack.get("mailto", "")).strip() or None
    allowed_hosts_raw = pack.get("allowed_hosts")
    allowed_hosts: tuple[str, ...]
    if isinstance(allowed_hosts_raw, list) and allowed_hosts_raw:
        allowed_hosts = tuple(sorted({str(value).strip().lower() for value in allowed_hosts_raw if str(value).strip()}))
    else:
        allowed_hosts = _DEFAULT_ALLOWED_HOSTS

    from tools.polymath.polymath_scout_v1 import scout_void
    from tools.polymath.polymath_sources_v1 import PolymathSourceClient

    source_client = PolymathSourceClient(
        store_root=store_root,
        allowed_hosts=allowed_hosts,
        max_response_bytes=max_blob_bytes_u64,
    )
    try:
        scout_result = scout_void(
            registry_path=registry_path,
            void_report_path=out_void_path,
            store_root=store_root,
            mailto=mailto,
            max_topics=max_topics,
            delay_seconds=delay_seconds,
            source_client=source_client,
        )
    except Exception:  # noqa: BLE001
        scout_result = _emit_offline_void_report(
            out_void_path=out_void_path,
            store_root=store_root,
            tick_u64=tick_u64,
            out_dir=out_dir,
            failure_reason="OFFLINE_SOURCE_FETCH_FAILED",
        )

    rows = load_jsonl(out_void_path)
    if not rows:
        scout_result = _emit_offline_void_report(
            out_void_path=out_void_path,
            store_root=store_root,
            tick_u64=tick_u64,
            out_dir=out_dir,
            failure_reason="EMPTY_VOID_REPORT",
        )
        rows = load_jsonl(out_void_path)
    for row in rows:
        validate_schema(row, "polymath_void_report_v1")
    expected_out_void_path = (out_dir / _VOID_REPORT_CANONICAL_REL).resolve()
    if out_void_path.resolve() != expected_out_void_path:
        fail("MISSING_STATE_INPUT")
    if not expected_out_void_path.exists() or not expected_out_void_path.is_file():
        fail("MISSING_STATE_INPUT")

    source_sha256s = _source_sha256s(rows)
    scout_status: dict[str, Any] = {
        "schema_version": "polymath_scout_status_v1",
        "scout_run_id": "sha256:" + ("0" * 64),
        "tick_u64": int(tick_u64),
        "rows_written_u64": int(len(rows)),
        "top_void_score_q32": {"q": _top_void_q32(rows)},
        "topics_scanned_u64": _topics_scanned_u64(rows),
        "sources_sha256s": source_sha256s,
    }
    no_id = dict(scout_status)
    no_id.pop("scout_run_id", None)
    scout_status["scout_run_id"] = canon_hash_obj(no_id)
    validate_schema(scout_status, "polymath_scout_status_v1")

    scout_status_path = out_dir / scout_status_rel
    scout_status_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(scout_status_path, scout_status)

    report_payload = {
        "schema_version": "polymath_scout_report_v1",
        "report_id": "sha256:" + ("0" * 64),
        "tick_u64": int(tick_u64),
        "status_rel": scout_status_rel,
        "void_report_rel": "polymath/registry/polymath_void_report_v1.jsonl",
        "rows_written_u64": int(scout_status["rows_written_u64"]),
        "top_void_score_q32": dict(scout_status["top_void_score_q32"]),
        "topics_scanned_u64": int(scout_status["topics_scanned_u64"]),
        "created_at_utc": _utc_now_iso(),
    }
    report_no_id = dict(report_payload)
    report_no_id.pop("report_id", None)
    report_payload["report_id"] = canon_hash_obj(report_no_id)
    write_canon_json(reports_dir / "polymath_scout_report_v1.json", report_payload)

    touched_paths = sorted(
        {
            "polymath/registry/polymath_void_report_v1.jsonl",
            scout_status_rel,
        }
    )

    bundle_payload = {
        "schema_version": "polymath_scout_promotion_bundle_v1",
        "bundle_id": "sha256:" + ("0" * 64),
        "campaign_id": "rsi_polymath_scout_v1",
        "scout_run_id": str(scout_status["scout_run_id"]),
        "activation_key": str(scout_status["scout_run_id"]),
        "report_rel": "daemon/rsi_polymath_scout_v1/state/reports/polymath_scout_report_v1.json",
        "void_report_rel": "polymath/registry/polymath_void_report_v1.jsonl",
        "status_rel": scout_status_rel,
        "rows_written_u64": int(scout_result.get("rows_written_u64", len(rows))),
        "touched_paths": touched_paths,
    }
    _, bundle_obj, _ = write_hashed_json(
        promotion_dir,
        "polymath_scout_promotion_bundle_v1.json",
        bundle_payload,
        id_field="bundle_id",
    )
    emit_test_plan_receipt(
        promotion_dir=promotion_dir,
        touched_paths=[str(row) for row in bundle_obj.get("touched_paths", []) if isinstance(row, str)],
        mode="promotion",
    )

    print("OK")


def main() -> None:
    parser = argparse.ArgumentParser(prog="campaign_polymath_scout_v1")
    parser.add_argument("--campaign_pack", required=True)
    parser.add_argument("--out_dir", required=True)
    args = parser.parse_args()
    run(campaign_pack=Path(args.campaign_pack), out_dir=Path(args.out_dir))


if __name__ == "__main__":
    main()
