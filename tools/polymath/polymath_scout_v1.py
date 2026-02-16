#!/usr/bin/env python3
"""Deterministic polymath void scouting over sealed public-source responses (v1)."""

from __future__ import annotations

import argparse
import json
import sys
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    _value = str(_entry)
    if _value not in sys.path:
        sys.path.insert(0, _value)

from cdel.v1_7r.canon import write_jsonl_line
from cdel.v18_0.omega_common_v1 import Q32_ONE, canon_hash_obj, fail, load_canon_dict, rat_q32, validate_schema
from tools.polymath.polymath_sources_v1 import PolymathSourceClient


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _normalize_domain_id(text: str) -> str:
    out = []
    prev_sep = False
    for ch in str(text).strip().lower():
        if ch.isalnum():
            out.append(ch)
            prev_sep = False
            continue
        if not prev_sep:
            out.append("_")
            prev_sep = True
    slug = "".join(out).strip("_")
    return slug or "domain_unknown"


def _openalex_topics(payload: dict[str, Any], *, max_topics: int) -> list[dict[str, Any]]:
    rows = payload.get("results")
    if not isinstance(rows, list):
        fail("SCHEMA_FAIL")
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        topic_id = str(row.get("id", "")).strip()
        topic_name = str(row.get("display_name", "")).strip()
        if not topic_id or not topic_name:
            continue
        out.append(
            {
                "cited_by_count": max(0, int(row.get("cited_by_count", 0))),
                "topic_id": topic_id,
                "topic_name": topic_name,
            }
        )
    out.sort(key=lambda row: (str(row["topic_id"]), str(row["topic_name"])))
    return out[: max(1, int(max_topics))]


def _arxiv_total_results(xml_text: str) -> int:
    if not xml_text.strip():
        return 0
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return 0
    namespaces = {
        "atom": "http://www.w3.org/2005/Atom",
        "open": "http://a9.com/-/spec/opensearch/1.1/",
    }
    total = root.findtext("open:totalResults", default="0", namespaces=namespaces)
    try:
        return max(0, int(total))
    except Exception:
        return 0


def _crossref_total_results(payload: dict[str, Any]) -> int:
    message = payload.get("message")
    if not isinstance(message, dict):
        return 0
    try:
        return max(0, int(message.get("total-results", 0)))
    except Exception:
        return 0


def _semantic_scholar_total_results(payload: dict[str, Any]) -> int:
    total_raw = payload.get("total")
    if isinstance(total_raw, int):
        return max(0, int(total_raw))
    rows = payload.get("data")
    if isinstance(rows, list):
        return max(0, len(rows))
    return 0


def _source_evidence(url: str, sealed: dict[str, Any]) -> dict[str, str]:
    sha256 = str(sealed.get("sha256", ""))
    if not sha256.startswith("sha256:"):
        fail("SCHEMA_FAIL")
    receipt_path = Path(str(sealed.get("receipt_path", "")))
    receipt_payload = load_canon_dict(receipt_path)
    receipt_sha = canon_hash_obj(receipt_payload)
    return {
        "receipt_sha256": receipt_sha,
        "sha256": sha256,
        "url": str(url),
    }


def _registry_domain_rows(registry_path: Path) -> list[dict[str, Any]]:
    payload = load_canon_dict(registry_path)
    if payload.get("schema_version") != "polymath_domain_registry_v1":
        fail("SCHEMA_FAIL")
    validate_schema(payload, "polymath_domain_registry_v1")
    rows = payload.get("domains")
    if not isinstance(rows, list):
        fail("SCHEMA_FAIL")
    out: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            out.append(row)
    return out


def _coverage_q32(*, domain_rows: list[dict[str, Any]], topic_id: str, candidate_domain_id: str) -> int:
    for row in domain_rows:
        if str(row.get("domain_id", "")).strip() == candidate_domain_id:
            return Q32_ONE
        topic_ids = row.get("topic_ids")
        if isinstance(topic_ids, list) and topic_id in {str(x) for x in topic_ids}:
            return Q32_ONE
    return 0


def _safe_q32_from_signal(*, value: int, max_value: int) -> int:
    if max_value <= 0 or value <= 0:
        return 0
    return rat_q32(value, max_value)


def scout_void(
    *,
    registry_path: Path,
    void_report_path: Path,
    store_root: Path | None = None,
    mailto: str | None = None,
    max_topics: int = 12,
    delay_seconds: float = 1.0,
    source_client: PolymathSourceClient | None = None,
) -> dict[str, Any]:
    domain_rows = _registry_domain_rows(registry_path)
    client = source_client or PolymathSourceClient(store_root=store_root)

    openalex = client.openalex_topics(per_page=max(1, int(max_topics)), mailto=mailto)
    topics = _openalex_topics(openalex["payload"], max_topics=max_topics)

    signal_rows: list[dict[str, Any]] = []
    for topic in topics:
        topic_name = str(topic["topic_name"])
        arxiv = client.arxiv_query(search_query=f"all:{topic_name}", max_results=1)
        time.sleep(max(0.0, float(delay_seconds)))
        crossref = client.crossref_works(query=topic_name, rows=1, mailto=mailto)
        time.sleep(max(0.0, float(delay_seconds)))
        s2 = client.semantic_scholar_paper_search(query=topic_name, limit=1)

        signal_rows.append(
            {
                "candidate_domain_id": _normalize_domain_id(topic_name),
                "evidence": [
                    _source_evidence(openalex["url"], openalex["sealed"]),
                    _source_evidence(arxiv["url"], arxiv["sealed"]),
                    _source_evidence(crossref["url"], crossref["sealed"]),
                    _source_evidence(s2["url"], s2["sealed"]),
                ],
                "signals": {
                    "arxiv": _arxiv_total_results(str(arxiv["payload"].get("xml", ""))),
                    "crossref": _crossref_total_results(crossref["payload"]),
                    "openalex": int(topic["cited_by_count"]),
                    "semantic_scholar": _semantic_scholar_total_results(s2["payload"]),
                },
                "topic_id": str(topic["topic_id"]),
                "topic_name": topic_name,
            }
        )

    maxima = {
        "openalex": max([int(row["signals"]["openalex"]) for row in signal_rows] + [0]),
        "arxiv": max([int(row["signals"]["arxiv"]) for row in signal_rows] + [0]),
        "crossref": max([int(row["signals"]["crossref"]) for row in signal_rows] + [0]),
        "semantic_scholar": max([int(row["signals"]["semantic_scholar"]) for row in signal_rows] + [0]),
    }

    out_rows: list[dict[str, Any]] = []
    for row in signal_rows:
        sig = row["signals"]
        openalex_q = _safe_q32_from_signal(value=int(sig["openalex"]), max_value=maxima["openalex"])
        arxiv_q = _safe_q32_from_signal(value=int(sig["arxiv"]), max_value=maxima["arxiv"])
        crossref_q = _safe_q32_from_signal(value=int(sig["crossref"]), max_value=maxima["crossref"])
        s2_q = _safe_q32_from_signal(value=int(sig["semantic_scholar"]), max_value=maxima["semantic_scholar"])

        weighted = (4 * openalex_q) + (2 * arxiv_q) + (2 * crossref_q) + (2 * s2_q)
        trend_q32 = weighted // 10

        candidate_domain_id = str(row["candidate_domain_id"])
        coverage_q32 = _coverage_q32(
            domain_rows=domain_rows,
            topic_id=str(row["topic_id"]),
            candidate_domain_id=candidate_domain_id,
        )
        void_q32 = (int(trend_q32) * (Q32_ONE - int(coverage_q32))) >> 32

        payload = {
            "candidate_domain_id": candidate_domain_id,
            "coverage_score_q32": {"q": int(coverage_q32)},
            "row_id": "sha256:" + ("0" * 64),
            "scanned_at_utc": _utc_now_iso(),
            "schema_version": "polymath_void_report_v1",
            "source_evidence": list(row["evidence"]),
            "topic_id": str(row["topic_id"]),
            "topic_name": str(row["topic_name"]),
            "trend_score_q32": {"q": int(trend_q32)},
            "void_score_q32": {"q": int(void_q32)},
        }
        no_id = dict(payload)
        no_id.pop("row_id", None)
        payload["row_id"] = canon_hash_obj(no_id)
        validate_schema(payload, "polymath_void_report_v1")
        out_rows.append(payload)

    out_rows.sort(key=lambda value: (str(value["topic_id"]), str(value["candidate_domain_id"])))
    for row in out_rows:
        write_jsonl_line(void_report_path, row)

    sorted_void = sorted(out_rows, key=lambda value: (-int(value["void_score_q32"]["q"]), str(value["topic_id"])))
    return {
        "rows_written_u64": len(out_rows),
        "top_rows": sorted_void[:5],
        "void_report_path": void_report_path.as_posix(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="polymath_scout_v1")
    parser.add_argument("--registry_path", default="polymath/registry/polymath_domain_registry_v1.json")
    parser.add_argument("--void_report_path", default="polymath/registry/polymath_void_report_v1.jsonl")
    parser.add_argument("--store_root", default="")
    parser.add_argument("--mailto", default="")
    parser.add_argument("--max_topics", type=int, default=12)
    parser.add_argument("--delay_seconds", type=float, default=1.0)
    args = parser.parse_args()

    store_root = Path(args.store_root).resolve() if str(args.store_root).strip() else None
    result = scout_void(
        registry_path=(Path(args.registry_path).resolve()),
        void_report_path=(Path(args.void_report_path).resolve()),
        store_root=store_root,
        mailto=str(args.mailto).strip() or None,
        max_topics=max(1, int(args.max_topics)),
        delay_seconds=max(0.0, float(args.delay_seconds)),
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
